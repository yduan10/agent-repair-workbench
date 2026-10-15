"""Immutable host-owned copies; caller must durably claim BEFORE invoking writes.

This is not a filesystem/database transaction. An uncertain publish must be reconciled,
never automatically retried. Limits of two candidates and request dedup belong to caller.
Local owner is trusted: readonly modes/hash checks do not stop malicious same-UID writers.
The executor must verify both before and after execution. Never import or exec source here.
"""

from __future__ import annotations

import ast
import ctypes
import difflib
import errno
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from agent_workbench.candidates.contracts import (
    CandidateError,
    CandidatePatch,
    SafeDiff,
    SnapshotRef,
)
from agent_workbench.controlled_tools.resources import (
    CaseManifest,
    read_verified,
)
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.mcp_config import ROOT, canonical, digest
from agent_workbench.repair_cases.bindings import validate_baseline_binding
from agent_workbench.repair_cases.profiles import (
    CaseProfile,
    RepairCaseId,
    get_profile,
    profile_for_manifest,
)

SOURCE_ROOT = ROOT / "examples" / "analysis"
SOURCE_SHA256 = "357abe9daaf18b22c9ed8cd7ca5d3f31776a20afdea7b82b0a66d753316f8712"
MAX_FILE = 131072
START_LINE, END_LINE = 107, 110
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True)
class SnapshotHandle:
    """Private host capability; only .ref may be serialized for API or persistence."""

    ref: SnapshotRef
    _root: Path = field(repr=False)

    @property
    def root(self) -> Path:
        """For the trusted executor's mount, never an API field."""
        return self._root


def _same(a: os.stat_result, b: os.stat_result) -> bool:
    return (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns, a.st_mode) == (
        b.st_dev,
        b.st_ino,
        b.st_size,
        b.st_mtime_ns,
        b.st_ctime_ns,
        b.st_mode,
    )


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    parts = path.absolute().parts
    if parts[0] != "/" or any(part in ("", ".", "..") for part in parts[1:]):
        raise CandidateError("SNAPSHOT_PATH_REJECTED")
    descriptors: list[int] = []
    try:
        fd = os.open("/", DIRECTORY_FLAGS)
        descriptors.append(fd)
        for part in parts[1:]:
            fd = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            descriptors.append(fd)
        yield fd
    except OSError:
        raise CandidateError("SNAPSHOT_IO_ERROR") from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _read(fd: int, *, readonly: bool) -> bytes:
    before_dir = os.fstat(fd)
    if set(os.listdir(fd)) != {"server.py"}:
        raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
    if readonly and stat.S_IMODE(before_dir.st_mode) != 0o555:
        raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
    file_fd = os.open(
        "server.py", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd
    )
    try:
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise CandidateError("SNAPSHOT_FILE_REJECTED")
        if readonly and stat.S_IMODE(before.st_mode) != 0o444:
            raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
        if before.st_size > MAX_FILE:
            raise CandidateError("SNAPSHOT_LIMIT_EXCEEDED")
        data = bytearray()
        while len(data) <= MAX_FILE:
            block = os.read(file_fd, min(8192, MAX_FILE + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > MAX_FILE:
            raise CandidateError("SNAPSHOT_LIMIT_EXCEEDED")
        after = os.fstat(file_fd)
        entry = os.stat("server.py", dir_fd=fd, follow_symlinks=False)
        if not _same(before, after) or not _same(after, entry):
            raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
        if set(os.listdir(fd)) != {"server.py"} or not _same(before_dir, os.fstat(fd)):
            raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
        try:
            bytes(data).decode("utf-8")
        except UnicodeError:
            raise CandidateError("SNAPSHOT_ENCODING_INVALID") from None
        return bytes(data)
    finally:
        os.close(file_fd)


def _tree(raw: bytes) -> str:
    return digest(canonical({"server.py": digest(raw)}))


def _frozen_source(profile: CaseProfile | None = None) -> bytes:
    profile = profile or get_profile("output_mismatch")
    source_root = (
        SOURCE_ROOT if profile.case_id == "output_mismatch" else ROOT / profile.resource_directory
    )
    try:
        manifest = CaseManifest.model_validate_json(
            read_verified(source_root, "manifest.json", profile.manifest_sha256)
        )
        if (
            manifest.source.path != "source/server.py"
            or manifest.source.sha256 != profile.source_sha256
            or (manifest.source.start_line, manifest.source.end_line) != (START_LINE, END_LINE)
        ):
            raise CandidateError("SOURCE_MANIFEST_MISMATCH")
        return read_verified(source_root, "source/server.py", profile.source_sha256)
    except (ResourceError, ValidationError):
        raise CandidateError("SOURCE_MANIFEST_MISMATCH") from None


def _parse(raw: bytes) -> ast.Module:
    if len(raw) > MAX_FILE:
        raise CandidateError("SNAPSHOT_LIMIT_EXCEEDED")
    try:
        return ast.parse(raw.decode("utf-8"), filename="server.py", type_comments=True)
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        raise CandidateError("PATCH_SYNTAX_INVALID") from None


def _validate_change(base: bytes, changed: bytes) -> None:
    lines = base.splitlines(keepends=True)
    prefix, suffix = b"".join(lines[: START_LINE - 1]), b"".join(lines[END_LINE:])
    if not changed.startswith(prefix) or not changed.endswith(suffix):
        raise CandidateError("PATCH_SCOPE_REJECTED")
    snippet = changed[len(prefix) : -len(suffix)]
    if len(snippet) > 8192:
        raise CandidateError("SNAPSHOT_LIMIT_EXCEEDED")
    if not snippet.startswith(lines[START_LINE - 1]):
        raise CandidateError("PATCH_SCOPE_REJECTED")
    if any(line.strip() and not line.startswith(b"    ") for line in snippet.splitlines()[1:]):
        raise CandidateError("PATCH_SCOPE_REJECTED")
    try:
        _compare_ast(base, changed)
    except RecursionError:
        raise CandidateError("PATCH_SYNTAX_INVALID") from None


def _compare_ast(base: bytes, changed: bytes) -> None:
    old, new = _parse(base), _parse(changed)
    if len(old.body) != len(new.body):
        raise CandidateError("PATCH_SCOPE_REJECTED")
    target_count = 0
    for first, second in zip(old.body, new.body, strict=True):
        if isinstance(first, ast.FunctionDef) and first.name == "lookup_result":
            target_count += 1
            if not isinstance(second, ast.FunctionDef) or second.name != first.name:
                raise CandidateError("PATCH_SCOPE_REJECTED")
            # Compare all function fields except its body; annotations, decorators,
            # defaults, async/type parameters and type comments must stay unchanged.
            for name in first._fields:
                if name == "body":
                    continue
                left, right = getattr(first, name), getattr(second, name)
                if isinstance(left, ast.AST):
                    equal = isinstance(right, ast.AST) and ast.dump(left) == ast.dump(right)
                elif isinstance(left, list):
                    equal = [ast.dump(v) for v in left] == [ast.dump(v) for v in right]
                else:
                    equal = left == right
                if not equal:
                    raise CandidateError("PATCH_SCOPE_REJECTED")
        elif ast.dump(first) != ast.dump(second):
            raise CandidateError("PATCH_SCOPE_REJECTED")
    if target_count != 1:
        raise CandidateError("PATCH_SCOPE_REJECTED")


def _replace(base: bytes, replacement: str) -> bytes:
    lines = base.splitlines(keepends=True)
    prefix, suffix = b"".join(lines[: START_LINE - 1]), b"".join(lines[END_LINE:])
    raw = replacement.encode("utf-8")
    if not raw.endswith(b"\n"):
        raw += b"\n"
    if not raw.startswith(lines[START_LINE - 1]):
        raise CandidateError("PATCH_SCOPE_REJECTED")
    changed = prefix + raw + suffix
    if changed == base:
        raise CandidateError("PATCH_EMPTY")
    _validate_change(base, changed)
    return changed


def _rename_exclusive(parent: int, source: str, destination: str) -> None:
    """Atomic no-replace, including an already-existing EMPTY destination directory."""
    libc = ctypes.CDLL(None, use_errno=True)
    symbol, flags = ("renameatx_np", 4) if sys.platform == "darwin" else ("renameat2", 1)
    if sys.platform not in ("darwin", "linux") or not hasattr(libc, symbol):
        raise CandidateError("ATOMIC_PUBLISH_UNAVAILABLE")
    rename = getattr(libc, symbol)
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent, source.encode(), parent, destination.encode(), flags) != 0:
        error = ctypes.get_errno()
        if error in (errno.EEXIST, errno.ENOTEMPTY):
            raise CandidateError("SNAPSHOT_ID_CONFLICT")
        if error in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
            raise CandidateError("ATOMIC_PUBLISH_UNAVAILABLE")
        raise CandidateError("SNAPSHOT_IO_ERROR")


class SnapshotStore:
    """Host-owned root. No model may supply this path or authorization manifest."""

    def __init__(self, root: Path):
        self.root = root.absolute()

    @contextmanager
    def _root(self, *, create: bool = False) -> Iterator[int]:
        with _directory(self.root.parent) as parent:
            if create:
                try:
                    os.mkdir(self.root.name, 0o700, dir_fd=parent)
                    os.fsync(parent)
                except FileExistsError:
                    pass
            try:
                fd = os.open(self.root.name, DIRECTORY_FLAGS, dir_fd=parent)
                info = os.fstat(fd)
                if info.st_uid != os.getuid() or info.st_mode & 0o022:
                    os.close(fd)
                    raise CandidateError("SNAPSHOT_PATH_REJECTED")
                try:
                    yield fd
                finally:
                    os.close(fd)
            except OSError:
                raise CandidateError("SNAPSHOT_IO_ERROR") from None

    def _publish(self, ref: SnapshotRef, raw: bytes) -> SnapshotHandle:
        name = ".staging-" + str(uuid4())
        with self._root(create=True) as root:
            stage: int | None = None
            published = False
            try:
                os.mkdir(name, 0o700, dir_fd=root)
                stage = os.open(name, DIRECTORY_FLAGS, dir_fd=root)
                fd = os.open(
                    "server.py",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=stage,
                )
                try:
                    view = memoryview(raw)
                    while view:
                        written = os.write(fd, view)
                        if written <= 0:
                            raise CandidateError("SNAPSHOT_IO_ERROR")
                        view = view[written:]
                    os.fchmod(fd, 0o444)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.fchmod(stage, 0o555)
                os.fsync(stage)
                if _read(stage, readonly=True) != raw:
                    raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
                if not _same(os.fstat(stage), os.stat(name, dir_fd=root, follow_symlinks=False)):
                    raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
                _rename_exclusive(root, name, ref.snapshot_id)
                published = True
                try:
                    os.fsync(root)
                except OSError:
                    # Rename may already be durable. Preserve it for explicit reconciliation.
                    raise CandidateError("SNAPSHOT_COMMIT_UNKNOWN") from None
            except OSError:
                raise CandidateError("SNAPSHOT_IO_ERROR") from None
            finally:
                if stage is not None:
                    if not published:
                        # Only this freshly created staging inode; no recursive path deletion.
                        try:
                            os.fchmod(stage, 0o700)
                            os.unlink("server.py", dir_fd=stage)
                        except OSError:
                            pass
                    os.close(stage)
                    if not published:
                        try:
                            os.rmdir(name, dir_fd=root)
                        except OSError:
                            pass
        handle = SnapshotHandle(ref, self.root / ref.snapshot_id)
        try:
            self.verify(handle)
        except CandidateError:
            raise CandidateError("SNAPSHOT_COMMIT_UNKNOWN") from None
        return handle

    def create_baseline(
        self, snapshot_id: str, *, case_id: RepairCaseId = "output_mismatch"
    ) -> SnapshotHandle:
        try:
            profile = get_profile(case_id)
        except ValueError:
            raise CandidateError("SOURCE_MANIFEST_MISMATCH") from None
        raw = _frozen_source(profile)
        try:
            ref = SnapshotRef(
                snapshot_id=snapshot_id,
                kind="baseline",
                manifest_sha256=profile.manifest_sha256,
                file_sha256=digest(raw),
                tree_sha256=_tree(raw),
            )
        except ValidationError:
            raise CandidateError("SNAPSHOT_REQUEST_INVALID") from None
        return self._publish(ref, raw)

    def verify(self, handle: SnapshotHandle) -> bytes:
        try:
            ref = SnapshotRef.model_validate_json(handle.ref.model_dump_json())
        except (ValidationError, ValueError):
            raise CandidateError("SNAPSHOT_REQUEST_INVALID") from None
        try:
            profile = profile_for_manifest(ref.manifest_sha256)
        except ValueError:
            raise CandidateError("SNAPSHOT_PATH_REJECTED") from None
        if handle.root != self.root / ref.snapshot_id:
            raise CandidateError("SNAPSHOT_PATH_REJECTED")
        with self._root() as root:
            before = os.stat(ref.snapshot_id, dir_fd=root, follow_symlinks=False)
            fd = os.open(ref.snapshot_id, DIRECTORY_FLAGS, dir_fd=root)
            try:
                if not _same(before, os.fstat(fd)):
                    raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
                raw = _read(fd, readonly=True)
                if not _same(
                    os.fstat(fd), os.stat(ref.snapshot_id, dir_fd=root, follow_symlinks=False)
                ):
                    raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
            finally:
                os.close(fd)
        if digest(raw) != ref.file_sha256 or _tree(raw) != ref.tree_sha256:
            raise CandidateError("SNAPSHOT_CONTENT_MISMATCH")
        frozen = _frozen_source(profile)
        if ref.kind == "baseline":
            validate_baseline_binding(ref)
            if raw != frozen:
                raise CandidateError("SOURCE_MANIFEST_MISMATCH")
        else:
            if ref.baseline_tree_sha256 != _tree(frozen):
                raise CandidateError("PATCH_BASE_MISMATCH")
            _validate_change(frozen, raw)
        return raw

    def create_candidate(
        self, baseline: SnapshotHandle, candidate_id: str, patch: CandidatePatch
    ) -> SnapshotHandle:
        try:
            patch = CandidatePatch.model_validate_json(patch.model_dump_json())
        except (ValueError, ValidationError):
            raise CandidateError("PATCH_REQUEST_INVALID") from None
        base = self.verify(baseline)
        if baseline.ref.kind != "baseline":
            raise CandidateError("BASELINE_REQUIRED")
        if (
            patch.expected_baseline_hash != baseline.ref.tree_sha256
            or patch.expected_file_hash != baseline.ref.file_sha256
        ):
            raise CandidateError("PATCH_BASE_MISMATCH")
        changed = _replace(base, patch.replacement)
        try:
            ref = SnapshotRef(
                snapshot_id=candidate_id,
                kind="candidate",
                manifest_sha256=baseline.ref.manifest_sha256,
                file_sha256=digest(changed),
                tree_sha256=_tree(changed),
                baseline_id=baseline.ref.snapshot_id,
                baseline_tree_sha256=baseline.ref.tree_sha256,
                patch_sha256=digest(canonical(patch.model_dump(mode="json"))),
            )
        except ValidationError:
            raise CandidateError("SNAPSHOT_REQUEST_INVALID") from None
        self.verify(baseline)
        return self._publish(ref, changed)

    def diff(self, baseline: SnapshotHandle, candidate: SnapshotHandle) -> SafeDiff:
        base, changed = self.verify(baseline), self.verify(candidate)
        if (
            baseline.ref.kind != "baseline"
            or candidate.ref.kind != "candidate"
            or candidate.ref.manifest_sha256 != baseline.ref.manifest_sha256
            or candidate.ref.baseline_id != baseline.ref.snapshot_id
            or candidate.ref.baseline_tree_sha256 != baseline.ref.tree_sha256
        ):
            raise CandidateError("PATCH_BASE_MISMATCH")
        _validate_change(base, changed)
        result = "".join(
            difflib.unified_diff(
                base.decode().splitlines(keepends=True),
                changed.decode().splitlines(keepends=True),
                fromfile="baseline/source/server.py",
                tofile="candidate/source/server.py",
                n=3,
            )
        )
        if len(result.encode()) > 65536:
            raise CandidateError("SNAPSHOT_LIMIT_EXCEEDED")
        self.verify(baseline)
        self.verify(candidate)
        return SafeDiff(baseline=baseline.ref, candidate=candidate.ref, unified_diff=result)
