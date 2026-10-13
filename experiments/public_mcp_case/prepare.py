"""Verify the complete pinned source tree; explicit setup also fetches dependencies."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

COMMIT = "2118f14f8a19bc158d8a1cf90af58d85d187f849"
ARCHIVE_SHA256 = "c860806fd728927747fdc0b9624b824d545e48e4199e1be9cc94906f6e44aba9"
URL = f"https://codeload.github.com/modelcontextprotocol/python-sdk/tar.gz/{COMMIT}"
PROJECT = Path(__file__).resolve().parent
ARTIFACTS = PROJECT.parents[1] / "artifacts/public-mcp-case"


class VerificationError(Exception):
    """Only a fixed non-sensitive code crosses the CLI boundary."""


def sha256(path: Path) -> str:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise VerificationError("source_entry_invalid")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_manifest(archive: Path) -> tuple[dict[str, tuple[int, str]], set[str]]:
    """Read expected files and directories from the SHA-pinned official archive."""
    if sha256(archive) != ARCHIVE_SHA256:
        raise VerificationError("upstream_archive_hash_mismatch")
    files: dict[str, tuple[int, str]] = {}
    directories = {"."}
    root = f"python-sdk-{COMMIT}"
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            parts = PurePosixPath(member.name).parts
            if (
                not parts
                or parts[0] != root
                or ".." in parts
                or not (member.isfile() or member.isdir())
            ):
                raise VerificationError("unexpected_archive_entry")
            relative = PurePosixPath(*parts[1:])
            name = str(relative)
            directories.update(str(p) for p in relative.parents)
            if member.isdir():
                directories.add(name)
            else:
                if name in files:
                    raise VerificationError("unexpected_archive_entry")
                stream = bundle.extractfile(member)
                if stream is None:
                    raise VerificationError("unexpected_archive_entry")
                with stream:
                    files[name] = (member.size, hashlib.sha256(stream.read()).hexdigest())
    if files.keys() & directories:
        raise VerificationError("unexpected_archive_entry")
    return files, directories


def verify_source(artifacts: Path = ARTIFACTS, project: Path = PROJECT) -> dict[str, object]:
    """Pure read-only verification; no network, subprocess, install or artifact writes.

    Exact file AND directory sets are required. No cache exception: extra .py,
    sourceless .pyc and __pycache__ all fail. Callers must run Python with -I -B.
    Concurrent hostile filesystem replacement is outside this trusted-local experiment.
    """
    expected_files, expected_dirs = archive_manifest(artifacts / "python-sdk.tar.gz")
    source = artifacts / f"python-sdk-{COMMIT}"
    if not stat.S_ISDIR(source.lstat().st_mode):
        raise VerificationError("source_entry_invalid")
    seen_files: dict[str, str] = {}
    seen_dirs = {"."}
    pending = [source]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                name = path.relative_to(source).as_posix()
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode):
                    raise VerificationError("source_entry_invalid")
                if stat.S_ISDIR(mode):
                    if name not in expected_dirs:
                        raise VerificationError("source_tree_mismatch")
                    seen_dirs.add(name)
                    pending.append(path)
                elif stat.S_ISREG(mode):
                    expected = expected_files.get(name)
                    if expected is None:
                        raise VerificationError("source_tree_mismatch")
                    size, expected_digest = expected
                    if entry.stat(follow_symlinks=False).st_size != size:
                        raise VerificationError("upstream_source_modified")
                    actual_digest = sha256(path)
                    if actual_digest != expected_digest:
                        raise VerificationError("upstream_source_modified")
                    seen_files[name] = actual_digest
                else:
                    raise VerificationError("source_entry_invalid")
    if seen_files.keys() != expected_files.keys() or seen_dirs != expected_dirs:
        raise VerificationError("source_tree_mismatch")
    canonical = json.dumps(
        sorted(seen_files.items()), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return {
        "code": "source_verified",
        "commit": COMMIT,
        "archive_sha256": ARCHIVE_SHA256,
        "lock_sha256": sha256(project / "uv.lock"),
        "source_tree_sha256": hashlib.sha256(canonical).hexdigest(),
        "source_files_verified": len(seen_files),
        "source_modified": False,
    }


def prepare_environment() -> dict[str, object]:
    """Explicit setup only; never entered by --verify-only."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    archive = ARTIFACTS / "python-sdk.tar.gz"
    if not archive.exists() or sha256(archive) != ARCHIVE_SHA256:
        partial = archive.with_suffix(".partial")
        subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                "180",
                "--output",
                str(partial),
                URL,
            ],
            check=True,
            timeout=185,
            capture_output=True,
        )
        if sha256(partial) != ARCHIVE_SHA256:
            raise VerificationError("upstream_archive_hash_mismatch")
        partial.replace(archive)
    archive_manifest(archive)
    source = ARTIFACTS / f"python-sdk-{COMMIT}"
    if not source.exists():
        with tempfile.TemporaryDirectory(dir=ARTIFACTS, prefix="extract-") as staging:
            with tarfile.open(archive) as bundle:
                bundle.extractall(staging, filter="data")
            (Path(staging) / source.name).rename(source)
    # Existing polluted trees fail. Never erase user paths or silently repair evidence.
    manifest = verify_source()
    uv = shutil.which("uv")
    if uv is None:
        raise VerificationError("uv_required")
    install_env = {
        key: os.environ[key]
        for key in ("HOME", "PATH", "TMPDIR", "SYSTEMROOT")
        if key in os.environ
    }
    install_env.update(UV_HTTP_TIMEOUT="20", UV_HTTP_RETRIES="1")
    subprocess.run(
        [uv, "sync", "--frozen", "--project", str(PROJECT), "--python", "3.12"],
        check=True,
        timeout=120,
        env=install_env,
        capture_output=True,
    )
    (ARTIFACTS / "source-verification.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--verify-only"]):
        print(json.dumps({"code": "invalid_arguments"}))
        return 2
    try:
        result = verify_source() if args else prepare_environment()
    except VerificationError as exc:
        print(json.dumps({"code": str(exc)}))
        return 2
    except (OSError, ValueError, tarfile.TarError):
        print(json.dumps({"code": "source_unavailable"}))
        return 2
    except subprocess.SubprocessError:
        print(json.dumps({"code": "environment_prepare_failed"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
