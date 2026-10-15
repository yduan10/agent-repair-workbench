"""Opt-in P0-06 host death recovery: real Docker/SQLite, no model calls.

The test operator explicitly authorizes SIGSTOP/SIGKILL of the test owner and
exact rm --force of its persisted attempts, including still-running containers.
State must be created under the repository's Docker-shared artifacts directory.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution.compare import ComparisonPlan
from agent_workbench.candidate_execution.docker import CandidateDockerControl, verified_image
from agent_workbench.candidate_execution.oracle import ORACLE_SHA256, SUITE_SHA256
from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_recovery.inventory import RecoveryInventory
from agent_workbench.repair_recovery.service import RecoveryService
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairTask
from agent_workbench.repair_store.reproduction_models import ReproductionPlan, reproduction_id
from agent_workbench.repair_store.reproductions import ReproductionStore
from agent_workbench.runner.docker import DockerControl

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.environ.get("AWB_REPAIR_RECOVERY_DOCKER") != "1",
    reason="explicit real Docker recovery gate required",
)


def uid():
    return str(uuid4())


def cas(saved, fence):
    return dict(
        expected_revision=saved.task.revision, expected_sha256=saved.task_sha256, fence=fence
    )


async def owner(directory, image_root, mode):
    """Independent process: persist all identities BEFORE creating a real container."""
    image = verified_image(image_root)
    store = ReproductionStore(directory)
    store.initialize()
    snapshots = SnapshotStore(directory / "repair-snapshots")
    baseline = snapshots.create_baseline(uid())
    task = RepairTask(
        task_id=uid(),
        baseline=baseline.ref,
        mode="three_role",
        started_at=datetime.now(UTC),
        budget=Budget(total_tokens=1000, output_tokens=100),
    )
    with RepairFence(directory, task.task_id) as fence:
        saved = store.create_task(task, fence=fence)
        if mode == "T05":
            request_id = uid()
            plan = ReproductionPlan(
                task_id=task.task_id,
                request_id=request_id,
                attempt_id=reproduction_id(task.task_id, request_id),
                baseline=baseline.ref,
                suite_sha256=SUITE_SHA256,
                oracle_sha256=ORACLE_SHA256,
                image_id=image.image_id,
                image_source_sha256=image.source_sha256,
            )
            saved = store.reserve_reproduction(
                plan,
                role="diagnosis",
                baseline=baseline,
                image_root=image_root,
                **cas(saved, fence),
            )
            attempt, snapshot = plan.attempt_id, baseline
        else:
            patch = CandidatePatch(
                expected_baseline_hash=baseline.ref.tree_sha256,
                expected_file_hash=baseline.ref.file_sha256,
                replacement=(
                    "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
                    '    return {"count": count}\n'
                ),
            )
            pending = store.reserve_candidate(
                task.task_id, uid(), uid(), "repair", patch, **cas(saved, fence)
            )
            candidate = snapshots.create_candidate(baseline, pending.candidate.candidate_id, patch)
            saved = store.finish_candidate(
                pending.claim, snapshot=candidate.ref, **cas(pending, fence)
            )
            plan = ComparisonPlan(
                task_id=task.task_id,
                request_id=uid(),
                comparison_id=uid(),
                baseline=baseline.ref,
                candidate=candidate.ref,
                attempts=tuple(uid() for _ in range(4)),
                suite_sha256=SUITE_SHA256,
                oracle_sha256=ORACLE_SHA256,
                image_id=image.image_id,
                image_source_sha256=image.source_sha256,
            )
            saved = store.reserve_comparison(
                plan,
                role="verification",
                baseline=baseline,
                candidate=candidate,
                image_root=image_root,
                **cas(saved, fence),
            )
            # The candidate slot exercises snapshot binding as well as baseline identities.
            attempt, snapshot = plan.attempts[2], candidate
        (directory / "owned.json").write_text(json.dumps({"task_id": task.task_id}))
        docker = await DockerControl.connect()
        controller = CandidateDockerControl(docker, snapshot, image, "wrong_type", attempt)
        cid = await controller.create()
        await controller.verify()
        await docker.command("start", cid)
        inspected = await controller.inspect()
        assert inspected["State"]["Running"] is True
        (directory / "ready.json").write_text(
            json.dumps(
                dict(
                    task_id=task.task_id,
                    attempt_id=attempt,
                    container_id=cid,
                    usage=saved.task.usage.model_dump(mode="json"),
                )
            )
        )
        # Owner intentionally does not perform cleanup: parent tests fatal process death.
        await asyncio.Event().wait()


@pytest.mark.parametrize("mode", ["T05", "T07"])
def test_sigkill_inspect_then_explicit_exact_reap(mode):
    image_root = Path(os.environ["AWB_REPAIR_RECOVERY_IMAGE_ROOT"]).resolve()
    directory = ROOT / "artifacts" / "recovery-docker" / uid()
    directory.mkdir(parents=True)
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), str(directory), str(image_root), mode],
        cwd=ROOT,
        env={
            "PATH": os.environ["PATH"],
            "HOME": os.environ["HOME"],
            "PYTHONPATH": str(ROOT / "src"),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    store = RecoveryInventory(directory)
    ready = None
    try:
        deadline = time.monotonic() + 25
        while not (directory / "ready.json").exists():
            assert child.poll() is None, "test owner exited before readiness"
            assert time.monotonic() < deadline, "test owner readiness timed out"
            time.sleep(0.05)
        ready = json.loads((directory / "ready.json").read_text())
        before = store.get(ready["task_id"])
        child.send_signal(signal.SIGSTOP)
        blocked = asyncio.run(
            RecoveryService(store, image_root).recover(ready["task_id"], apply=True)
        )
        assert blocked.error == "OWNER_ACTIVE" and not blocked.resources
        child.kill()
        child.wait(timeout=5)
        report = asyncio.run(RecoveryService(store, image_root).recover(ready["task_id"]))
        present = [r for r in report.resources if r.state == "present"]
        assert len(present) == 1 and present[0].running is True
        assert present[0].attempt_id == ready["attempt_id"]
        assert store.get(ready["task_id"]) == before
        result = asyncio.run(
            RecoveryService(store, image_root).recover(ready["task_id"], apply=True)
        )
        assert result.exit_code() == 0 and result.ledger_reconciled
        assert result.outcome == "outcome_unknown" and any(
            r.state == "removed" for r in result.resources
        )
        after = store.get(ready["task_id"])
        assert after.task.usage == before.task.usage
        repeated = asyncio.run(
            RecoveryService(store, image_root).recover(ready["task_id"], apply=True)
        )
        assert repeated.exit_code() == 0 and all(r.state == "absent" for r in repeated.resources)
        assert store.get(ready["task_id"]) == after
        (directory / "acceptance.json").write_text(
            json.dumps(
                {
                    "mode": mode,
                    "model": "not_called",
                    "docker": "real",
                    "owner": "SIGSTOP_then_SIGKILL",
                    "inspect": report.model_dump(mode="json"),
                    "apply": result.model_dump(mode="json"),
                    "usage_retained": True,
                    "repeated_apply_unchanged": True,
                },
                indent=2,
            )
        )
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        # Only test-owned persisted targets; never prune or enumerate unrelated Docker state.
        if ready is None and (directory / "owned.json").exists():
            ready = json.loads((directory / "owned.json").read_text())
        if ready:
            asyncio.run(RecoveryService(store, image_root).recover(ready["task_id"], apply=True))
        store.close()


if __name__ == "__main__":
    asyncio.run(owner(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]))
