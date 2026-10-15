"""H4 real SQLite/API case identity; no model or container execution."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_workbench.api import create_app
from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_reader.models import RepairDetail, RepairList
from agent_workbench.repair_reader.reader import RepairReader, task_view
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import Mutation, RepairTask
from agent_workbench.repair_store.store import RepairStore


def seed_cases(directory: Path) -> list[str]:
    store = RepairStore(directory)
    store.initialize()
    snapshots = SnapshotStore(directory / "repair-snapshots")
    ids = []
    for case in ("output_mismatch", "counter_offset"):
        baseline = snapshots.create_baseline(str(uuid4()), case_id=case)
        task = RepairTask(
            task_id=str(uuid4()),
            baseline=baseline.ref,
            mode="three_role",
            started_at=datetime.now(UTC),
            budget=Budget(total_tokens=2_000_000, output_tokens=8192),
        )
        with RepairFence(directory, task.task_id) as fence:
            store.create_task(task, fence=fence)
        ids.append(task.task_id)
    store.close()
    return ids


def test_two_case_ids_derived_from_real_baselines_and_api(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    ids = seed_cases(directory)
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    with TestClient(create_app(), base_url="http://127.0.0.1:8030") as client:
        listing = client.get("/api/repairs").json()
        assert listing["schema_version"] == 2
        assert {r["case_id"] for r in listing["repairs"]} == {"output_mismatch", "counter_offset"}
        for task_id, case in zip(ids, ("output_mismatch", "counter_offset"), strict=True):
            detail = client.get(f"/api/repairs/{task_id}").json()
            assert detail["schema_version"] == 2 and detail["task"]["case_id"] == case
            assert "failure_code" not in str(detail) and "claim_sha256" not in str(detail)
            detail["schema_version"] = 1
            with pytest.raises(ValidationError):
                RepairDetail.model_validate(detail)
        listing["schema_version"] = 1
        with pytest.raises(ValidationError):
            RepairList.model_validate(listing)


@pytest.mark.parametrize("field", ["manifest_sha256", "file_sha256", "tree_sha256"])
def test_case_identity_unknown_or_inconsistent_profile_refused(tmp_path, field):
    directory = tmp_path / "state"
    task_id = seed_cases(directory)[0]
    reader = RepairReader(directory, tmp_path)
    try:
        saved = reader.store.get(task_id)
        bad = saved.task.model_copy(
            update={"baseline": saved.task.baseline.model_copy(update={field: "f" * 64})}
        )
        with pytest.raises(CandidateError, match="SOURCE_MANIFEST_MISMATCH"):
            task_view(Mutation(task=bad, task_sha256=saved.task_sha256))
    finally:
        reader.close()
