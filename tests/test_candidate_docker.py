"""Policy negatives plus explicitly opted-in real Docker behavioral and cleanup gates."""

import asyncio
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest

from agent_workbench.candidate_execution import oracle
from agent_workbench.candidate_execution.docker import CandidateDockerControl, verified_image
from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.runner.docker import DockerControl, DockerFailure

ROOT = Path(__file__).resolve().parents[1]
DOCKER = pytest.mark.skipif(
    os.getenv("AWB_CANDIDATE_DOCKER_TEST") != "1",
    reason="explicit P0-06 Docker gate; no automatic image build",
)
SIGNATURE = "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"


def candidate(store, baseline, body):
    return store.create_candidate(
        baseline,
        str(uuid4()),
        CandidatePatch(
            expected_baseline_hash=baseline.ref.tree_sha256,
            expected_file_hash=baseline.ref.file_sha256,
            replacement=SIGNATURE + body,
        ),
    )


@pytest.fixture
def snapshots():
    # This Docker VM shares the checkout, not arbitrary macOS private temporary paths.
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p006-test-", dir=artifacts) as folder:
        store = SnapshotStore(Path(folder))
        yield store, store.create_baseline(str(uuid4()))


def test_image_tamper_rejected_without_start(tmp_path, snapshots):
    _, base = snapshots
    output = asyncio.run(
        oracle.run_oracle(base, scenario="pass", attempt_id=str(uuid4()), image_root=tmp_path)
    )
    assert output.status == "inconclusive" and output.error == "image_unverified"
    assert output.cleanup == "not_created" and all(s.status == "not_run" for s in output.steps)


def test_native_double_cancel_waits_for_owned_cleanup(monkeypatch, snapshots):
    _, base = snapshots

    async def exercise():
        began, cleaned = asyncio.Event(), asyncio.Event()

        async def operation(snapshot, report, *args):
            try:
                began.set()
                await anyio.sleep_forever()
            finally:
                with anyio.CancelScope(shield=True):
                    await anyio.sleep(0.05)
                    report.cleanup = "removed"
                    cleaned.set()
            return report

        monkeypatch.setattr(oracle, "_execute", operation)
        task = asyncio.create_task(
            oracle.run_oracle(base, scenario="pass", attempt_id=str(uuid4()), image_root=ROOT)
        )
        await began.wait()
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        output = await task
        assert cleaned.is_set() and output.status == "cancelled"

    asyncio.run(exercise())


@DOCKER
@pytest.mark.docker
def test_real_baseline_and_correct_candidate_both_scenarios(snapshots):
    store, base = snapshots
    fixed = candidate(store, base, '    return {"count": count}\n')

    async def exercise():
        receipts = []
        for snapshot in (base, fixed):
            for scenario in ("wrong_type", "pass"):
                output = await oracle.run_oracle(
                    snapshot, scenario=scenario, attempt_id=str(uuid4()), image_root=ROOT
                )
                expected = "failed" if snapshot == base and scenario == "wrong_type" else "passed"
                assert output.status == expected, output.model_dump_json()
                assert output.cleanup == "removed" and output.snapshot_verified_after
                assert all(s.status != "not_run" for s in output.steps)
                assert (await DockerControl.connect()).endpoint.startswith("unix://")
                receipts.append(output.model_dump())
        (ROOT / "artifacts/p006-real-oracle.json").write_text(json.dumps(receipts, indent=2))

    asyncio.run(exercise())


@DOCKER
@pytest.mark.docker
@pytest.mark.parametrize(
    "body,expected",
    [
        ('    return {"count": 1}\n', "failed"),
        ('    return {"count": True}\n', "failed"),
        ('    return {"count": float(count)}\n', "failed"),
        (
            '    globals()["output_schema"] = lambda _: {"type": "object"}\n'
            '    return {"count": count}\n',
            "failed",
        ),
        (
            '    print("{\\"all_passed\\": true}", flush=True)\n    return {"count": count}\n',
            "inconclusive",
        ),
        ("    os._exit(0)\n", "inconclusive"),
        ('    time.sleep(30)\n    return {"count": count}\n', "inconclusive"),
        (
            "    os.kill(os.getppid(), signal.SIGSTOP)\n"
            '    time.sleep(30)\n    return {"count": count}\n',
            "inconclusive",
        ),
    ],
)
def test_real_untrusted_candidate_never_decides_pass(snapshots, body, expected):
    store, base = snapshots
    snapshot = candidate(store, base, body)

    async def exercise():
        output = await oracle.run_oracle(
            snapshot,
            scenario="wrong_type",
            attempt_id=str(uuid4()),
            image_root=ROOT,
            stage_timeout=1,
        )
        assert output.status == expected, output.model_dump_json()
        assert output.cleanup == "removed" and output.snapshot_verified_after
        if expected == "inconclusive":
            assert any(s.status == "not_run" for s in output.steps)

    asyncio.run(exercise())


@DOCKER
@pytest.mark.docker
def test_real_native_repeated_cancel_reclaims_actual_container(snapshots, monkeypatch):
    store, base = snapshots
    snapshot = candidate(store, base, '    time.sleep(30)\n    return {"count": count}\n')

    async def exercise():
        called = asyncio.Event()
        original = oracle.SequenceOracle.phase

        async def phase(self, action):
            result = await original(self, action)
            if self.step("initialize").status == "passed":
                called.set()
            return result

        monkeypatch.setattr(oracle.SequenceOracle, "phase", phase)
        attempt = str(uuid4())
        task = asyncio.create_task(
            oracle.run_oracle(snapshot, scenario="pass", attempt_id=attempt, image_root=ROOT)
        )
        await asyncio.wait_for(called.wait(), 5)
        await asyncio.sleep(0.1)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        output = await asyncio.wait_for(task, 12)
        assert output.status == "cancelled" and output.cleanup == "removed", (
            output.model_dump_json()
        )
        control = await DockerControl.connect()
        listing = await control.command(
            "container",
            "ls",
            "--all",
            "--filter",
            f"name=^/awb-p006-{attempt}$",
            "--format",
            "{{.ID}}",
        )
        assert listing.strip() == b""

    asyncio.run(exercise())


@DOCKER
@pytest.mark.docker
def test_real_snapshot_hash_rechecked_after_execution(snapshots, monkeypatch):
    store, base = snapshots
    snapshot = candidate(store, base, '    return {"count": count}\n')
    original = CandidateDockerControl.cleanup

    async def cleanup(self):
        result = await original(self)
        file = self.snapshot.root / "server.py"
        file.chmod(0o644)
        file.write_bytes(file.read_bytes() + b"# changed\n")
        file.chmod(0o444)
        return result

    monkeypatch.setattr(CandidateDockerControl, "cleanup", cleanup)
    output = asyncio.run(
        oracle.run_oracle(snapshot, scenario="pass", attempt_id=str(uuid4()), image_root=ROOT)
    )
    assert output.status == "inconclusive" and output.error == "snapshot_unverified"
    assert output.cleanup == "removed" and not output.snapshot_verified_after


@DOCKER
@pytest.mark.docker
def test_real_policy_rejects_added_writable_mount_or_environment(snapshots, monkeypatch):
    _, snapshot = snapshots

    async def exercise():
        docker = await DockerControl.connect()
        controlled = CandidateDockerControl(
            docker, snapshot, verified_image(ROOT), "pass", str(uuid4())
        )
        try:
            await controlled.create()
            await controlled.verify()
            actual = await controlled.inspect()
            assert actual is not None

            async def altered():
                return actual

            monkeypatch.setattr(controlled, "inspect", altered)
            actual["Mounts"][0]["RW"] = True
            with pytest.raises(DockerFailure, match="container_policy_mismatch"):
                await controlled.verify()
            actual["Mounts"][0]["RW"] = False
            actual["Config"]["Env"].append("UNEXPECTED_SECRET=synthetic")
            with pytest.raises(DockerFailure, match="container_policy_mismatch"):
                await controlled.verify()
            monkeypatch.undo()
        finally:
            assert await controlled.cleanup()

    asyncio.run(exercise())


def load(name):
    path = ROOT / "containers/p0_06" / (name + ".py")
    spec = importlib.util.spec_from_file_location("p006_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("prepare")
IMAGE = "sha256:" + "a" * 64


def inspected_image(image_id=IMAGE, **overrides):
    config = {
        "Entrypoint": list(prepare.EXPECTED_ENTRYPOINT),
        "User": "65532:65532",
        "WorkingDir": "/tmp",
        "Volumes": None,
        "Env": list(prepare.EXPECTED_ENV),
    }
    config.update(overrides)
    return json.dumps([{"Id": image_id, "Config": config}])


def write_iid(argv, value=IMAGE):
    Path(argv[argv.index("--iidfile") + 1]).write_text(value + "\n")


@pytest.fixture
def source(tmp_path, monkeypatch):
    directory = tmp_path / "fixture"
    directory.mkdir()
    for name in prepare.SOURCE_FILES:
        (directory / name).write_text(name + " fixture")
    monkeypatch.setattr(prepare, "SOURCE_DIR", directory)
    monkeypatch.setattr(prepare, "PROJECT_ROOT", tmp_path)
    original_hash = prepare.source_sha256
    monkeypatch.setattr(prepare, "source_sha256", lambda: original_hash(directory))
    return directory


def test_hash_algorithm_and_tamper(tmp_path):
    for name in prepare.SOURCE_FILES:
        (tmp_path / name).write_text(name)
    expected = hashlib.sha256(
        b"\0".join(name.encode() + b"\0" + name.encode() for name in prepare.SOURCE_FILES)
    ).hexdigest()
    assert prepare.source_sha256(tmp_path) == expected
    (tmp_path / "supervisor.py").write_text("changed")
    assert prepare.source_sha256(tmp_path) != expected


def test_source_symlink_rejected(tmp_path):
    (tmp_path / "target").write_text("ignored")
    (tmp_path / "Dockerfile").symlink_to(tmp_path / "target")
    with pytest.raises(ValueError, match="source_unavailable"):
        prepare.source_sha256(tmp_path)


def test_build_offline_minimal_context_atomic_manifest(source, monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert kwargs["check"] is True
        assert kwargs["timeout"] <= 120
        if argv[1] == "build":
            context = Path(argv[-1])
            assert {p.name for p in context.iterdir()} == {"Dockerfile", "supervisor.py"}
            assert "--network=none" in argv
            assert "--pull=false" in argv
            assert f"BASE={prepare.BASE_DIGEST}" in argv
            assert argv[argv.index("--tag") + 1] == "awb-p0-06:local"
            iidfile = Path(argv[argv.index("--iidfile") + 1])
            assert iidfile.parent == context.parent
            assert not iidfile.is_relative_to(context)
            write_iid(argv)
        return SimpleNamespace(stdout=inspected_image())

    monkeypatch.setattr(prepare.subprocess, "run", run)
    result = prepare.prepare()
    assert calls[0][0] == ["docker", "image", "inspect", prepare.BASE_DIGEST]
    assert calls[-1][0] == ["docker", "image", "inspect", IMAGE]
    assert result == {
        "image_id": IMAGE,
        "source_sha256": prepare.source_sha256(),
        "base_digest": prepare.BASE_DIGEST,
    }
    artifacts = prepare.PROJECT_ROOT / "artifacts"
    assert json.loads((artifacts / "p0-06-image.json").read_text()) == result
    assert len(list(artifacts.iterdir())) == 1


@pytest.mark.parametrize(
    "failure", ["missing_base", "build_failure", "bad_image", "changed_source"]
)
def test_prepare_failure_never_replaces_manifest(source, monkeypatch, failure):
    artifacts = prepare.PROJECT_ROOT / "artifacts"
    artifacts.mkdir()
    manifest = artifacts / "p0-06-image.json"
    manifest.write_text("prior")
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if failure == "missing_base":
            raise subprocess.CalledProcessError(1, argv)
        if argv[1] == "build" and failure == "build_failure":
            raise subprocess.CalledProcessError(1, argv)
        if argv[1] == "build" and failure == "changed_source":
            (source / "supervisor.py").write_text("mutated")
        if argv[1] == "build":
            write_iid(argv, "bad" if failure == "bad_image" else IMAGE)
        return SimpleNamespace(stdout=inspected_image())

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        prepare.prepare()
    assert manifest.read_text() == "prior"
    if failure == "missing_base":
        assert len(calls) == 1


def test_concurrent_retag_does_not_select_another_build(source, monkeypatch):
    other = "sha256:" + "b" * 64
    tag_target = IMAGE
    inspections = []

    def run(argv, **kwargs):
        nonlocal tag_target
        if argv[1] == "build":
            write_iid(argv)
            tag_target = other  # Another build moves the tag before this build is inspected.
            return SimpleNamespace(stdout="")
        inspections.append(argv[-1])
        selected = tag_target if argv[-1] == prepare.IMAGE_TAG else argv[-1]
        return SimpleNamespace(stdout=inspected_image(selected))

    monkeypatch.setattr(prepare.subprocess, "run", run)
    assert prepare.prepare()["image_id"] == IMAGE
    assert inspections == [prepare.BASE_DIGEST, IMAGE]
    assert tag_target == other


@pytest.mark.parametrize(
    "config",
    [
        {"Entrypoint": ["sh", "-c", "untrusted"]},
        {"Entrypoint": None},
        {"User": "root"},
        {"WorkingDir": "/root"},
        {"Volumes": {"/data": {}}},
        {"Env": list(prepare.EXPECTED_ENV) + ["EXTRA=untrusted"]},
        {"Env": list(prepare.EXPECTED_ENV) + [prepare.EXPECTED_ENV[0]]},
        {"Env": ["PATH=/malicious/bin"]},
        {"Env": None},
        {"Env": [42]},
    ],
)
def test_bad_config_never_replaces_manifest(source, monkeypatch, config):
    artifacts = prepare.PROJECT_ROOT / "artifacts"
    artifacts.mkdir()
    manifest = artifacts / "p0-06-image.json"
    manifest.write_text("prior")

    def run(argv, **kwargs):
        if argv[1] == "build":
            write_iid(argv)
        return SimpleNamespace(stdout=inspected_image(**config))

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises(ValueError, match="invalid_image_config"):
        prepare.prepare()
    assert manifest.read_text() == "prior"


@pytest.mark.parametrize(
    "payload", ["{}", "[]", "[null]", "invalid", inspected_image("sha256:" + "b" * 64)]
)
def test_invalid_inspection_refuses_manifest(source, monkeypatch, payload):
    def run(argv, **kwargs):
        if argv[1] == "build":
            write_iid(argv)
        return SimpleNamespace(stdout=payload)

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises(ValueError):
        prepare.prepare()
    assert not (prepare.PROJECT_ROOT / "artifacts" / "p0-06-image.json").exists()


@pytest.mark.parametrize("value", [None, "sha256:" + "a" * 12, "x" * 129])
def test_missing_or_incomplete_iid_never_falls_back_to_tag(source, monkeypatch, value):
    inspected = []

    def run(argv, **kwargs):
        if argv[1] == "build" and value is not None:
            write_iid(argv, value)
        elif argv[1] == "image":
            inspected.append(argv[-1])
        return SimpleNamespace(stdout=inspected_image())

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises(ValueError, match="invalid_image_id"):
        prepare.prepare()
    assert inspected == [prepare.BASE_DIGEST]


@pytest.mark.parametrize(
    "error,code",
    [
        (OSError("SECRET_VALUE"), "image_prepare_failed"),
        (subprocess.TimeoutExpired(["SECRET_VALUE"], 120), "image_prepare_timeout"),
    ],
)
def test_error_output_redacted(monkeypatch, capsys, error, code):
    monkeypatch.setattr(sys, "argv", ["prepare.py"])

    def fail():
        raise error

    monkeypatch.setattr(prepare, "prepare", fail)
    assert prepare.main() == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert json.loads(out.err) == {"code": code}
    assert "SECRET_VALUE" not in out.err


def test_unknown_arguments_do_not_execute(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["prepare.py", "SECRET_VALUE"])
    monkeypatch.setattr(prepare, "prepare", lambda: pytest.fail("must not execute"))
    assert prepare.main() == 2
    assert json.loads(capsys.readouterr().err) == {"code": "invalid_arguments"}
