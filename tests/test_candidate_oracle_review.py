"""Independent B2 real-container probes; opt-in and no automatic image preparation."""

import asyncio
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution.docker import CandidateDockerControl, verified_image
from agent_workbench.candidate_execution.oracle import run_oracle
from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.runner.docker import DockerControl, DockerFailure

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.getenv("AWB_CANDIDATE_DOCKER_TEST") != "1", reason="explicit P0-06 Docker gate"
    ),
]


@pytest.fixture
def snapshot_factory():
    with tempfile.TemporaryDirectory(prefix="p006-review-", dir=ROOT / "artifacts") as directory:
        store = SnapshotStore(Path(directory))
        baseline = store.create_baseline(str(uuid4()))

        def create(body):
            return store.create_candidate(
                baseline,
                str(uuid4()),
                CandidatePatch(
                    expected_baseline_hash=baseline.ref.tree_sha256,
                    expected_file_hash=baseline.ref.file_sha256,
                    replacement="def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
                    + body,
                ),
            )

        yield create


@pytest.mark.parametrize(
    "body",
    [
        '    original = globals()["emit"]\n'
        "    def duplicate(identifier, result):\n"
        "        original(identifier, result)\n"
        "        original(identifier, result)\n"
        '    globals()["emit"] = duplicate\n'
        '    return {"count": count}\n',
        '    os.write(2, b"x" * 70000)\n    return {"count": count}\n',
    ],
)
def test_real_raw_duplicate_or_stderr_flood_never_passes(snapshot_factory, body):
    snapshot = snapshot_factory(body)
    result = asyncio.run(
        run_oracle(snapshot, scenario="pass", attempt_id=str(uuid4()), image_root=ROOT)
    )
    assert result.status == "inconclusive" and result.error == "wire_error"
    assert result.cleanup == "removed" and result.snapshot_verified_after
    assert any(step.status == "not_run" for step in result.steps)


def test_real_candidate_cannot_write_mount_and_container_constraints_hold(snapshot_factory):
    snapshot = snapshot_factory(
        "    observed = policy_probe()\n"
        "    try:\n"
        "        fd = os.open(__file__, os.O_WRONLY)\n"
        "    except OSError as error:\n"
        '        observed["root_write_denied"] = error.errno in (errno.EROFS, errno.EACCES)\n'
        "    else:\n"
        "        os.close(fd)\n"
        '    expected = {"uid_nonzero": True, "root_write_denied": True,\n'
        '        "only_loopback": True, "no_host_secret": True,\n'
        '        "cpu_max": "50000 100000", "memory_max": "134217728", "pids_max": "32"}\n'
        '    return {"count": count if observed == expected else "policy_violation"}\n'
    )
    result = asyncio.run(
        run_oracle(snapshot, scenario="pass", attempt_id=str(uuid4()), image_root=ROOT)
    )
    assert result.status == "passed", result.model_dump_json()
    assert result.cleanup == "removed" and result.snapshot_verified_after


def test_existing_attempt_is_not_adopted_started_or_removed(snapshot_factory):
    snapshot = snapshot_factory('    return {"count": count}\n')

    async def exercise():
        docker = await DockerControl.connect()
        attempt = str(uuid4())
        owner = CandidateDockerControl(docker, snapshot, verified_image(ROOT), "pass", attempt)
        visitor = CandidateDockerControl(docker, snapshot, verified_image(ROOT), "pass", attempt)
        try:
            original = await owner.create()
            await owner.verify()
            with pytest.raises(DockerFailure, match="^attempt_already_exists$"):
                await visitor.create()
            assert await visitor.cleanup()
            remaining = await owner.inspect()
            assert remaining is not None and remaining["Id"] == original
            assert remaining["State"]["Running"] is False
        finally:
            assert await owner.cleanup()

    asyncio.run(exercise())
