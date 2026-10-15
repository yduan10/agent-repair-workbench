"""P0-06 B1a: byte/AST boundaries and actual filesystem failure probes; no execution."""

import errno
import json
import os
import stat
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_workbench.candidates import snapshots as module
from agent_workbench.candidates.contracts import CandidateError, CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore
from agent_workbench.mcp_config import canonical, digest

HEADER = "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
FIX = HEADER + '    return {"count": count}\n'


@pytest.fixture
def store(tmp_path):
    value = SnapshotStore(tmp_path / "snapshots")
    yield value
    # Published directories are intentionally immutable, so pytest's cleanup needs owner chmod.
    for root, _directories, files in os.walk(tmp_path, followlinks=False):
        if not Path(root).is_symlink():
            os.chmod(root, 0o700)
        for file in files:
            path = Path(root) / file
            if not path.is_symlink() and path.is_file():
                os.chmod(path, 0o600)


@pytest.fixture
def baseline(store):
    return store.create_baseline(str(uuid4()))


def patch(base, replacement=FIX, **changes):
    return CandidatePatch(
        expected_baseline_hash=base.ref.tree_sha256,
        expected_file_hash=base.ref.file_sha256,
        replacement=replacement,
    ).model_copy(update=changes)


def test_valid_patch_preserves_baseline_outside_bytes_and_safe_metadata(store, baseline):
    original = module._frozen_source()
    candidate = store.create_candidate(baseline, str(uuid4()), patch(baseline))
    result = store.verify(candidate)
    lines = original.splitlines(keepends=True)
    assert result == b"".join(lines[:106]) + FIX.encode() + b"".join(lines[110:])
    assert store.verify(baseline) == original == module._frozen_source()
    assert stat.S_IMODE(candidate.root.stat().st_mode) == 0o555
    assert stat.S_IMODE((candidate.root / "server.py").stat().st_mode) == 0o444
    assert list(candidate.root.iterdir()) == [candidate.root / "server.py"]
    public = candidate.ref.model_dump_json()
    diff = store.diff(baseline, candidate)
    assert (
        "-    return" in diff.unified_diff and '+    return {"count": count}' in diff.unified_diff
    )
    assert str(store.root) not in public + diff.model_dump_json()
    assert "candidate_verified" not in public
    assert str(candidate.root) not in repr(candidate)
    assert candidate.ref.patch_sha256 == digest(canonical(patch(baseline).model_dump(mode="json")))
    assert candidate.ref.file_sha256 == digest(result)


@pytest.mark.parametrize(
    "replacement",
    [
        HEADER.replace("count: int", "count: str") + '    return {"count": count}\n',
        "@decorator\n" + FIX,
        HEADER + '    return {"count": count}\noutput_schema = lambda _: {}\n',
        HEADER + '    return {"count": count}\ndef second():\n    pass\n',
        HEADER + '    return {"count": count}\nimport secrets\n',
        HEADER + '    return {"count": count}\nclass Escape: pass\n',
        HEADER + 'return {"count": count}\n',
        HEADER.replace("def ", "async def ") + '    return {"count": count}\n',
        HEADER.replace("scenario: str", 'scenario: str = "pass"') + '    return {"count": count}\n',
        "def lookup_result(count, scenario):\n    return {}\n",
    ],
)
def test_signature_decorator_dedent_and_external_contract_changes_rejected(
    store, baseline, replacement
):
    before = set(store.root.iterdir())
    with pytest.raises(CandidateError):
        store.create_candidate(baseline, str(uuid4()), patch(baseline, replacement))
    assert set(store.root.iterdir()) == before
    assert store.verify(baseline) == module._frozen_source()


def test_no_host_execution_and_semantic_verdict_deferred(store, baseline):
    # Pure snapshot validation cannot claim this constant return is a correct repair.
    candidate = store.create_candidate(
        baseline, str(uuid4()), patch(baseline, HEADER + '    return {"count": 1}\n')
    )
    assert candidate.ref.kind == "candidate"
    assert not hasattr(candidate.ref, "candidate_verified")
    assert store.diff(baseline, candidate).candidate == candidate.ref


@pytest.mark.parametrize(
    "changes",
    [
        {"path": "../server.py"},
        {"path": "/secret/server.py"},
        {"path": "source/../server.py"},
        {"path": "source/other.py"},
        {"expected_file_hash": "0" * 64},
        {"expected_baseline_hash": "0" * 64},
        {"replacement": ""},
        {"replacement": "\ud800"},
        {"replacement": "\x00"},
        {"extra_file": "SECRET_PATH"},
    ],
)
def test_constructed_patch_revalidated_paths_hashes_and_multiple_file_shape(
    store, baseline, changes
):
    original = patch(baseline).model_dump()
    original.update(changes)
    if "extra_file" in original:
        with pytest.raises(ValidationError):
            CandidatePatch.model_validate(original)
    else:
        with pytest.raises(CandidateError):
            store.create_candidate(
                baseline, str(uuid4()), patch(baseline).model_copy(update=changes)
            )


def test_unicode_byte_limit_empty_and_original_id_rejected(store, baseline):
    with pytest.raises(ValidationError):
        patch(baseline, HEADER + "    #" + "中" * 2800 + "\n    return {}\n")
    original = b"".join(module._frozen_source().splitlines(keepends=True)[106:110]).decode()
    with pytest.raises(CandidateError, match="^PATCH_EMPTY$"):
        store.create_candidate(baseline, str(uuid4()), patch(baseline, original))
    with pytest.raises(CandidateError, match="^SNAPSHOT_REQUEST_INVALID$"):
        store.create_candidate(baseline, baseline.ref.snapshot_id, patch(baseline))
    assert store.verify(baseline) == module._frozen_source()


def test_each_candidate_starts_at_original_not_previous(store, baseline):
    first = store.create_candidate(baseline, str(uuid4()), patch(baseline))
    second = store.create_candidate(
        baseline, str(uuid4()), patch(baseline, HEADER + '    return {"count": 1}\n')
    )
    assert (
        first.ref.baseline_tree_sha256
        == second.ref.baseline_tree_sha256
        == baseline.ref.tree_sha256
    )
    with pytest.raises(CandidateError, match="^BASELINE_REQUIRED$"):
        store.create_candidate(first, str(uuid4()), patch(first))
    assert store.verify(first) != store.verify(second)


@pytest.mark.parametrize("existing", ["empty_directory", "snapshot", "symlink", "file"])
def test_atomic_collision_never_replaces_any_destination(store, baseline, existing):
    identifier = str(uuid4())
    target = store.root / identifier
    if existing == "snapshot":
        prior = store.create_candidate(baseline, identifier, patch(baseline))
    elif existing == "empty_directory":
        target.mkdir()
    elif existing == "symlink":
        target.symlink_to(baseline.root, target_is_directory=True)
    else:
        target.write_text("EXISTING")
    inode = target.lstat().st_ino
    with pytest.raises(CandidateError, match="^SNAPSHOT_ID_CONFLICT$"):
        store.create_candidate(baseline, identifier, patch(baseline))
    assert target.lstat().st_ino == inode
    assert not list(store.root.glob(".staging-*"))
    if existing == "snapshot":
        assert store.verify(prior)
    if existing == "file":
        assert target.read_text() == "EXISTING"


@pytest.mark.parametrize(
    "tamper", ["bytes", "extra_file", "extra_directory", "symlink", "hardlink", "fifo", "mode"]
)
def test_every_read_and_diff_reverify_full_directory_and_hash(store, baseline, tmp_path, tamper):
    candidate = store.create_candidate(baseline, str(uuid4()), patch(baseline))
    os.chmod(candidate.root, 0o700)
    file = candidate.root / "server.py"
    if tamper == "bytes":
        os.chmod(file, 0o600)
        file.write_bytes(
            file.read_bytes().replace(b'return {"count": count}', b'return {"count": False}')
        )
        os.chmod(file, 0o444)
    elif tamper == "extra_file":
        (candidate.root / "other.py").write_text("EXTRA")
    elif tamper == "extra_directory":
        (candidate.root / "empty").mkdir()
    elif tamper == "mode":
        os.chmod(file, 0o644)
    elif tamper == "hardlink":
        os.link(file, tmp_path / "external-link")
    else:
        file.unlink()
        if tamper == "symlink":
            file.symlink_to(baseline.root / "server.py")
        else:
            os.mkfifo(file)
    os.chmod(candidate.root, 0o555)
    with pytest.raises(CandidateError):
        store.verify(candidate)
    with pytest.raises(CandidateError):
        store.diff(baseline, candidate)


def test_root_ancestor_snapshot_and_handle_path_links_rejected(store, baseline, tmp_path):
    alias = tmp_path / "alias"
    alias.symlink_to(store.root, target_is_directory=True)
    with pytest.raises(CandidateError):
        SnapshotStore(alias / "nested").create_baseline(str(uuid4()))
    with pytest.raises(CandidateError):
        store.verify(replace(baseline, _root=tmp_path / "private"))
    target = store.root / str(uuid4())
    target.symlink_to(baseline.root, target_is_directory=True)
    fake = SnapshotHandle(baseline.ref.model_copy(update={"snapshot_id": target.name}), target)
    with pytest.raises(CandidateError):
        store.verify(fake)


@pytest.mark.parametrize("operation", ["write", "fsync", "rename"])
def test_filesystem_failure_leaves_no_published_candidate_or_changed_baseline(
    store, baseline, monkeypatch, operation
):
    original = module._frozen_source()
    identifier = str(uuid4())

    def fail(*args, **kwargs):
        raise OSError(errno.ENOSPC, "/PRIVATE/HOST/PATH")

    with monkeypatch.context() as m:
        m.setattr(
            module.os if operation != "rename" else module,
            {"write": "write", "fsync": "fsync", "rename": "_rename_exclusive"}[operation],
            fail,
        )
        with pytest.raises(CandidateError) as caught:
            store.create_candidate(baseline, identifier, patch(baseline))
        assert "PRIVATE" not in str(caught.value)
    assert not (store.root / identifier).exists()
    assert not list(store.root.glob(".staging-*"))
    assert store.verify(baseline) == original


def test_post_rename_fsync_failure_is_unknown_and_preserves_new_snapshot(
    store, baseline, monkeypatch
):
    identifier = str(uuid4())
    original_fsync = os.fsync

    def fail_parent(fd):
        if os.fstat(fd).st_ino == store.root.stat().st_ino:
            raise OSError(errno.ENOSPC, "PRIVATE")
        original_fsync(fd)

    with monkeypatch.context() as m:
        m.setattr(module.os, "fsync", fail_parent)
        with pytest.raises(CandidateError, match="^SNAPSHOT_COMMIT_UNKNOWN$"):
            store.create_candidate(baseline, identifier, patch(baseline))
    assert (store.root / identifier / "server.py").is_file()
    with pytest.raises(CandidateError, match="^SNAPSHOT_ID_CONFLICT$"):
        store.create_candidate(baseline, identifier, patch(baseline))


def test_unsupported_platform_fails_closed_and_staging_removed(store, baseline, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(module.sys, "platform", "unsupported")
        with pytest.raises(CandidateError, match="^ATOMIC_PUBLISH_UNAVAILABLE$"):
            store.create_candidate(baseline, str(uuid4()), patch(baseline))
    assert not list(store.root.glob(".staging-*"))


def test_changed_manifest_or_source_rejected_before_publish(store, baseline, monkeypatch, tmp_path):
    root = tmp_path / "source"
    (root / "source").mkdir(parents=True)
    manifest = module.SOURCE_ROOT / "manifest.json"
    (root / "manifest.json").write_bytes(manifest.read_bytes())
    (root / "source/server.py").write_bytes(module._frozen_source() + b"# changed\n")
    monkeypatch.setattr(module, "SOURCE_ROOT", root)
    with pytest.raises(CandidateError, match="^SOURCE_MANIFEST_MISMATCH$"):
        store.create_baseline(str(uuid4()))
    with pytest.raises(CandidateError, match="^SOURCE_MANIFEST_MISMATCH$"):
        store.verify(baseline)
    data = json.loads(manifest.read_bytes())
    data["source"]["start_line"] = 1
    (root / "manifest.json").write_text(json.dumps(data))
    with pytest.raises(CandidateError, match="^SOURCE_MANIFEST_MISMATCH$"):
        store.create_baseline(str(uuid4()))


def test_concurrent_publish_same_id_has_one_winner(store, baseline):
    from concurrent.futures import ThreadPoolExecutor

    identifier = str(uuid4())

    def publish():
        try:
            return store.create_candidate(baseline, identifier, patch(baseline))
        except CandidateError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: publish(), range(2)))
    assert sum(isinstance(item, SnapshotHandle) for item in result) == 1
    assert result.count("SNAPSHOT_ID_CONFLICT") == 1
    assert not list(store.root.glob(".staging-*"))


def test_full_snapshot_limit_and_mid_read_mutation_fail_closed(store, baseline, monkeypatch):
    candidate = store.create_candidate(baseline, str(uuid4()), patch(baseline))
    file = candidate.root / "server.py"
    original = file.read_bytes()
    inode = file.stat().st_ino
    os.chmod(file, 0o600)
    file.write_bytes(b"x" * (module.MAX_FILE + 1))
    os.chmod(file, 0o444)
    with pytest.raises(CandidateError, match="^SNAPSHOT_LIMIT_EXCEEDED$"):
        store.verify(candidate)
    os.chmod(file, 0o600)
    file.write_bytes(original)
    os.chmod(file, 0o444)
    actual_read = os.read
    changed = False

    def mutating_read(fd, count):
        nonlocal changed
        block = actual_read(fd, count)
        if not changed and os.fstat(fd).st_ino == inode:
            changed = True
            os.chmod(file, 0o600)
            file.write_bytes(original)
            os.chmod(file, 0o444)
        return block

    monkeypatch.setattr(module.os, "read", mutating_read)
    with pytest.raises(CandidateError, match="^SNAPSHOT_CONTENT_MISMATCH$"):
        store.verify(candidate)


def test_partial_writes_are_completed_before_publication(store, baseline, monkeypatch):
    original_write = os.write

    def short_write(fd, data):
        return original_write(fd, data[:7])

    monkeypatch.setattr(module.os, "write", short_write)
    candidate = store.create_candidate(baseline, str(uuid4()), patch(baseline))
    assert store.verify(candidate).count(b'    return {"count": count}\n') == 1


def test_diff_rejects_forged_hash_with_external_comment_change(store, baseline):
    candidate = store.create_candidate(baseline, str(uuid4()), patch(baseline))
    file = candidate.root / "server.py"
    raw = file.read_bytes().replace(
        b"from __future__ import annotations", b"# external\nfrom __future__ import annotations"
    )
    os.chmod(file, 0o600)
    file.write_bytes(raw)
    os.chmod(file, 0o444)
    forged = replace(
        candidate,
        ref=candidate.ref.model_copy(
            update={"file_sha256": digest(raw), "tree_sha256": module._tree(raw)}
        ),
    )
    with pytest.raises(CandidateError, match="^PATCH_SCOPE_REJECTED$"):
        store.diff(baseline, forged)
