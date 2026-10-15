"""Real temp ledger/snapshots, synthetic model/oracle; never invokes a container."""

import os
import sqlite3
from uuid import uuid4

import pytest

from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.repair_reader.reader import RepairReader
from agent_workbench.repair_store.reproductions import ReproductionStore
from agent_workbench.run_store.models import StoreError
from tests.agents.test_repair_controller import controller, execute
from tests.agents.test_repair_tool_bridge import ctx as ctx


@pytest.fixture
def completed(ctx):
    ctx.snapshots = SnapshotStore(ctx.store.directory / "repair-snapshots")
    ctx.baseline = ctx.snapshots.create_baseline(str(uuid4()))
    runtime, _ = controller(ctx, ["request_reproduction", "apply_candidate", "compare_candidate"])
    ctx.result = execute(runtime)
    assert ctx.result.cursor.task.outcome == "candidate_verified"
    ctx.reader = RepairReader(ctx.store.directory, ctx.image)
    ctx.task_id = ctx.result.cursor.task.task_id
    ctx.detail = ctx.reader.detail(ctx.task_id)
    ctx.candidate_id = ctx.detail.candidates[0].candidate_id
    ctx.comparison_id = ctx.detail.comparisons[0].comparison_id
    yield ctx
    ctx.reader.close()


def test_read_views_and_diff_verified_against_current_artifacts(completed):
    ctx = completed
    listing = ctx.reader.list(1)
    assert len(listing.repairs) == 1 and listing.repairs[0].task_id == ctx.task_id
    assert listing.repairs[0].recorded_outcome == "candidate_verified"
    detail = ctx.detail
    assert detail.candidates[0].snapshot_status == "verified"
    comparison = ctx.reader.comparison(ctx.task_id, ctx.comparison_id)
    assert (
        comparison.verification == "verified" and comparison.current_outcome == "candidate_verified"
    )
    assert len(comparison.slots) == 4 and all(len(item.steps) == 8 for item in comparison.slots)
    assert comparison.accepted is False
    diff = ctx.reader.diff(ctx.task_id, ctx.candidate_id)
    assert diff.diff.path == "source/server.py"
    assert '+    return {"count": count}' in diff.diff.unified_diff
    assert diff.diff.candidate.snapshot_id == ctx.candidate_id
    public = detail.model_dump_json() + diff.model_dump_json()
    for secret in (
        str(ctx.store.directory),
        "claim_sha256",
        "request_id",
        "replacement",
        "api_key",
    ):
        assert secret not in public


@pytest.mark.parametrize("target", ["candidate", "baseline"])
def test_tamper_revokes_current_verdict_and_refuses_diff(completed, target):
    ctx = completed
    snapshot = ctx.candidate_id if target == "candidate" else ctx.baseline.ref.snapshot_id
    path = ctx.snapshots.root / snapshot / "server.py"
    os.chmod(path, 0o600)
    path.write_text("DO_NOT_DISCLOSE_TAMPERED_SOURCE")
    detail = ctx.reader.detail(ctx.task_id)
    result = detail.comparisons[0]
    assert result.recorded_outcome == "candidate_verified"
    assert result.current_outcome is None and result.verification == "unavailable"
    assert result.slots == () and result.reason is None
    assert detail.candidates[0].snapshot_status == "unavailable"
    with pytest.raises((CandidateError, OSError)):
        ctx.reader.diff(ctx.task_id, ctx.candidate_id)
    assert "DO_NOT_DISCLOSE" not in detail.model_dump_json()


def test_image_version_change_revokes_comparison_but_not_snapshot(completed):
    ctx = completed
    (ctx.image / "containers/p0_06/supervisor.py").write_text("different version")
    detail = ctx.reader.detail(ctx.task_id)
    assert detail.candidates[0].snapshot_status == "verified"
    assert detail.comparisons[0].verification == "unavailable"
    assert detail.comparisons[0].current_outcome is None
    assert ctx.reader.diff(ctx.task_id, ctx.candidate_id).verification == "verified"


def test_candidate_path_symlink_not_followed(completed, tmp_path):
    ctx = completed
    path = ctx.snapshots.root / ctx.candidate_id
    os.chmod(path, 0o755)
    (path / "server.py").unlink()
    outside = tmp_path / "private"
    outside.write_text("PRIVATE_OUTSIDE_SOURCE")
    (path / "server.py").symlink_to(outside)
    with pytest.raises((CandidateError, OSError)):
        ctx.reader.diff(ctx.task_id, ctx.candidate_id)
    assert ctx.reader.detail(ctx.task_id).candidates[0].snapshot_status == "unavailable"
    assert outside.read_text() == "PRIVATE_OUTSIDE_SOURCE"


def test_cross_task_ids_rejected_even_for_existing_candidate_and_comparison(completed):
    ctx = completed
    with pytest.raises(StoreError, match="candidate_not_found"):
        ctx.reader.diff(ctx.cursor.task.task_id, ctx.candidate_id)
    with pytest.raises(StoreError, match="comparison_not_found"):
        ctx.reader.comparison(ctx.cursor.task.task_id, ctx.comparison_id)


@pytest.mark.parametrize("limit", [0, 51, -1, True, "20"])
def test_list_limit_strict(completed, limit):
    with pytest.raises(StoreError, match="invalid_limit"):
        completed.reader.list(limit)


def test_corrupt_ledger_not_returned_as_historical_success(completed):
    ctx = completed
    with sqlite3.connect(ctx.store._base.path) as db:
        db.execute("UPDATE repair_tasks SET sha256=? WHERE task_id=?", ("0" * 64, ctx.task_id))
    with pytest.raises(StoreError, match="store_corrupt"):
        ctx.reader.detail(ctx.task_id)
    with pytest.raises(StoreError, match="store_corrupt"):
        ctx.reader.list(1)


def test_missing_and_empty_database_reads_do_not_initialize(tmp_path):
    directory = tmp_path / "absent"
    reader = RepairReader(directory, tmp_path)
    try:
        assert reader.list(20).repairs == ()
        with pytest.raises(StoreError, match="not_found"):
            reader.detail(str(uuid4()))
        assert not directory.exists()
        store = ReproductionStore(directory)
        store.initialize()
        store.close()
        assert reader.list(20).repairs == ()
    finally:
        reader.close()


def test_old_schema_refused_without_migration(completed):
    ctx = completed
    with sqlite3.connect(ctx.store._base.path) as db:
        db.execute("UPDATE alembic_version SET version_num='0003_analyses'")
    with pytest.raises(StoreError, match="schema_incompatible"):
        ctx.reader.list(1)
    with sqlite3.connect(ctx.store._base.path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0003_analyses",
        )


def test_partial_then_unknown_comparison_has_no_current_verdict(ctx, monkeypatch):

    ctx.snapshots = SnapshotStore(ctx.store.directory / "repair-snapshots")
    ctx.baseline = ctx.snapshots.create_baseline(str(uuid4()))
    original = ctx.store.save_slot

    def fail_after_first(claim, item, **kwargs):
        original(claim, item, **kwargs)
        raise StoreError("store_unavailable")

    monkeypatch.setattr(ctx.store, "save_slot", fail_after_first)
    runtime, _ = controller(ctx, ["request_reproduction", "apply_candidate", "compare_candidate"])
    result = execute(runtime)
    assert result.requires_reconcile
    reader = RepairReader(ctx.store.directory, ctx.image)
    try:
        detail = reader.detail(result.cursor.task.task_id)
        comparison = detail.comparisons[0]
        assert comparison.status == "reserved" and comparison.verification == "not_finished"
        assert comparison.current_outcome is None and len(comparison.slots) == 1
        latest = ctx.store.get(result.cursor.task.task_id)
        ctx.store.reconcile_comparison(
            latest.task.task_id,
            expected_revision=latest.task.revision,
            expected_sha256=latest.task_sha256,
        )
        detail = reader.detail(latest.task.task_id)
        assert detail.task.recorded_outcome == "outcome_unknown"
        assert detail.comparisons[0].status == "outcome_unknown"
        assert detail.comparisons[0].current_outcome is None
    finally:
        reader.close()


@pytest.mark.parametrize(
    "change",
    [
        {"verification": "unavailable"},
        {"current_outcome": "rejected"},
        {"verification": "not_finished"},
        {"accepted": True},
        {"request_id": "PRIVATE_REQUEST"},
    ],
)
def test_public_comparison_shape_rejects_false_claims(completed, change):
    import json

    from pydantic import ValidationError

    from agent_workbench.repair_reader.models import ComparisonView

    value = completed.detail.comparisons[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        ComparisonView.model_validate_json(json.dumps({**value, **change}))
