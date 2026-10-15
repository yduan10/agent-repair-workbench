"""Opt-in B3c bridge test with actual SQLite, frozen snapshots and five real containers."""

import asyncio
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.mcp_config import ROOT
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_contracts.tools import ApplyCandidate, CompareCandidate
from agent_workbench.repair_runtime.tools import RepairToolBridge
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairTask
from agent_workbench.repair_store.reproductions import ReproductionStore

SIGNATURE = "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"

DOCKER = pytest.mark.skipif(
    os.getenv("AWB_CANDIDATE_DOCKER_TEST") != "1", reason="explicit prepared P0-06 image required"
)


def uid():
    return str(uuid4())


@DOCKER
@pytest.mark.parametrize(
    "body,expected",
    [
        ('    return {"count": count}\n', "candidate_verified"),
        ('    return {"count": 1}\n', "rejected"),
    ],
)
def test_real_five_container_repair_and_regression(body, expected):
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p006-bridge-", dir=artifacts) as directory:
        root = Path(directory)
        snapshots = SnapshotStore(root / "snapshots")
        baseline = snapshots.create_baseline(uid())
        store = ReproductionStore(root / "state")
        store.initialize()
        task_id = uid()
        budget = Budget(total_tokens=1000, output_tokens=100)
        registry = load_case(
            "output_mismatch", task_id=task_id, intent="propose_repair", budget=budget
        )
        task = RepairTask(
            task_id=task_id,
            baseline=baseline.ref,
            mode="single_role",
            started_at=datetime.now(UTC),
            budget=budget,
        )
        try:
            with RepairFence(store.directory, task_id) as fence:
                cursor = store.create_task(task, fence=fence)
                bridge = RepairToolBridge(
                    store=store,
                    registry=registry,
                    baseline=baseline,
                    snapshots=snapshots,
                    image_root=ROOT,
                    fence=fence,
                    remaining_seconds=lambda: 500.0,
                )
                reproduction = next(
                    r for r in registry.templates("diagnosis") if r.tool == "request_reproduction"
                )

                async def run():
                    reproduced = await bridge.execute("single", reproduction, cursor=cursor)
                    assert reproduced.response.payload.get("status") == "observed_failure", (
                        reproduced.response
                    )
                    applied = await bridge.execute(
                        "single",
                        ApplyCandidate(
                            tool="apply_candidate",
                            request_id=uid(),
                            candidate_id=uid(),
                            expected_baseline_hash=baseline.ref.tree_sha256,
                            expected_file_hash=baseline.ref.file_sha256,
                            replacement=SIGNATURE + body,
                            evidence_refs=reproduced.response.evidence_refs,
                        ),
                        cursor=reproduced.cursor,
                    )
                    assert applied.response.status == "ok", applied.response
                    compared = await bridge.execute(
                        "single",
                        CompareCandidate(
                            tool="compare_candidate",
                            request_id=uid(),
                            candidate_id=applied.response.payload["candidate_id"],
                            expected_candidate_tree_hash=applied.response.payload[
                                "candidate_tree_hash"
                            ],
                            evidence_refs=applied.response.evidence_refs,
                        ),
                        cursor=applied.cursor,
                    )
                    assert compared.response.payload.get("status") == expected, compared.response
                    record = store.comparisons(task_id)[0]
                    assert len(record.results) == 4
                    assert all(r.report.cleanup == "removed" for r in record.results)
                    assert compared.cursor.task.usage.tool_calls == 3
                    assert compared.response.payload["accepted"] is False

                asyncio.run(run())
        finally:
            store.close()
