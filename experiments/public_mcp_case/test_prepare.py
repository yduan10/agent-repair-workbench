"""Independent regression cases for complete-tree and read-only source verification."""

import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("prepare.py")
SPEC = importlib.util.spec_from_file_location("public_case_prepare", SCRIPT)
assert SPEC and SPEC.loader
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class SourceVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        prepare.ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=prepare.ARTIFACTS, prefix="verify-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        self.source = self.root / f"python-sdk-{prepare.COMMIT}"
        (self.source / "src").mkdir(parents=True)
        (self.source / "empty").mkdir()
        (self.source / "src/mcp.py").write_text("value = 1\n", encoding="utf-8")
        (self.source / "README.md").write_text("fixture\n", encoding="utf-8")
        archive = self.root / "python-sdk.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(self.source, arcname=self.source.name)
        expected_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.hash_patch = patch.object(prepare, "ARCHIVE_SHA256", expected_hash)
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    def verify(self) -> dict[str, object]:
        return prepare.verify_source(self.root, self.project)

    def reject(self, code: str) -> None:
        with self.assertRaisesRegex(prepare.VerificationError, "^" + code + "$"):
            self.verify()

    def test_clean_exact_tree_and_hash(self) -> None:
        result = self.verify()
        self.assertEqual(result["code"], "source_verified")
        self.assertEqual(result["source_files_verified"], 2)
        pairs = sorted(
            [p.relative_to(self.source).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()]
            for p in self.source.rglob("*")
            if p.is_file()
        )
        expected = hashlib.sha256(
            json.dumps(pairs, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(result["source_tree_sha256"], expected)

    def test_extra_importable_python(self) -> None:
        (self.source / "src/pydantic.py").write_text("raise RuntimeError()\n")
        self.reject("source_tree_mismatch")

    def test_extra_sourceless_bytecode(self) -> None:
        (self.source / "src/pydantic.pyc").write_bytes(b"injected")
        self.reject("source_tree_mismatch")

    def test_pycache_has_no_blanket_exception(self) -> None:
        cache = self.source / "src/__pycache__"
        cache.mkdir()
        (cache / "pydantic.cpython-312.pyc").write_bytes(b"injected")
        self.reject("source_tree_mismatch")

    def test_extra_empty_directory(self) -> None:
        (self.source / "src/extra").mkdir()
        self.reject("source_tree_mismatch")

    def test_missing_file(self) -> None:
        (self.source / "README.md").unlink()
        self.reject("source_tree_mismatch")

    def test_missing_empty_directory(self) -> None:
        (self.source / "empty").rmdir()
        self.reject("source_tree_mismatch")

    def test_same_size_content_tamper(self) -> None:
        (self.source / "src/mcp.py").write_text("value = 2\n")
        self.reject("upstream_source_modified")

    def test_file_symlink(self) -> None:
        target = self.source / "README.md"
        target.unlink()
        target.symlink_to(self.source / "src/mcp.py")
        self.reject("source_entry_invalid")

    def test_directory_symlink(self) -> None:
        held = self.root / "held-src"
        (self.source / "src").rename(held)
        (self.source / "src").symlink_to(held, target_is_directory=True)
        self.reject("source_entry_invalid")

    def test_source_root_symlink(self) -> None:
        held = self.root / "held-root"
        self.source.rename(held)
        self.source.symlink_to(held, target_is_directory=True)
        self.reject("source_entry_invalid")

    def test_archive_content_mismatch(self) -> None:
        with (self.root / "python-sdk.tar.gz").open("ab") as stream:
            stream.write(b"changed")
        self.reject("upstream_archive_hash_mismatch")

    def test_verify_only_never_installs_downloads_or_writes(self) -> None:
        original = prepare.verify_source
        with (
            patch.object(
                prepare, "verify_source", side_effect=lambda: original(self.root, self.project)
            ),
            patch.object(prepare, "prepare_environment", side_effect=AssertionError("setup")),
            patch.object(subprocess, "run", side_effect=AssertionError("subprocess")),
            patch.object(Path, "write_text", side_effect=AssertionError("write")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(prepare.main(["--verify-only"]), 0)
        self.assertEqual(json.loads(output.getvalue())["code"], "source_verified")
        self.assertFalse((self.root / "source-verification.json").exists())

    def test_failure_cli_uses_fixed_code(self) -> None:
        with (
            patch.object(prepare, "verify_source", side_effect=OSError("private/path secret")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(prepare.main(["--verify-only"]), 2)
        self.assertEqual(json.loads(output.getvalue()), {"code": "source_unavailable"})


class OfficialSourceVerificationTests(unittest.TestCase):
    def test_real_verify_only_under_five_seconds_without_mutations(self) -> None:
        def snapshot() -> dict[str, tuple[int, int]]:
            return {
                str(p.relative_to(prepare.ARTIFACTS)): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in prepare.ARTIFACTS.rglob("*")
                if p.is_file()
            }

        before = snapshot()
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-I", "-B", str(SCRIPT), "--verify-only"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(completed.returncode, 0, completed.stdout)
        result = json.loads(completed.stdout)
        self.assertEqual(result["source_files_verified"], 1717)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(snapshot(), before)
        self.assertLess(elapsed, 5)


if __name__ == "__main__":
    unittest.main()
