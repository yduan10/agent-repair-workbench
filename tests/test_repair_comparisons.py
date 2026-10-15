"""B1c real SQLite/snapshot checks with explicitly synthetic oracle reports; no Docker."""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import update

from agent_workbench.candidate_execution.compare import SLOTS, ComparisonPlan, SlotResult, compare
from agent_workbench.candidate_execution.models import STEPS, OracleReport, OracleStep
from agent_workbench.candidate_execution.oracle import ORACLE_SHA256, SUITE_SHA256
from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.mcp_config import digest
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_store.comparisons import ComparisonStore
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairClaim, RepairTask
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.schema import repair_comparison_attempts, repair_comparisons


def uid():
    return str(uuid4())


def cas(saved, fence):
    return dict(
        expected_revision=saved.task.revision, expected_sha256=saved.task_sha256, fence=fence
    )


@pytest.fixture
def ctx(tmp_path, request):
    store = ComparisonStore(tmp_path / "state")
    store.initialize()
    snapshots = SnapshotStore(tmp_path / "snapshots")
    baseline = snapshots.create_baseline(uid())
    task = RepairTask(
        task_id=uid(),
        baseline=baseline.ref,
        mode=getattr(request, "param", "three_role"),
        started_at=datetime.now(UTC),
        budget=Budget(total_tokens=1000, output_tokens=100),
    )
    fence = RepairFence(store.directory, task.task_id)
    fence.acquire()
    saved = store.create_task(task, fence=fence)
    patch = CandidatePatch(
        expected_baseline_hash=baseline.ref.tree_sha256,
        expected_file_hash=baseline.ref.file_sha256,
        replacement=(
            "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
            '    return {"count": count}\n'
        ),
    )
    pending = store.reserve_candidate(
        task.task_id,
        uid(),
        uid(),
        "single" if task.mode == "single_role" else "repair",
        patch,
        **cas(saved, fence),
    )
    candidate = snapshots.create_candidate(baseline, pending.candidate.candidate_id, patch)
    saved = store.finish_candidate(pending.claim, snapshot=candidate.ref, **cas(pending, fence))
    # Metadata-only image fixture; no image is built or executed by this test batch.
    image_root = tmp_path / "image"
    source = image_root / "containers/p0_06"
    source.mkdir(parents=True)
    parts = []
    for name in ("Dockerfile", "supervisor.py", "prepare.py"):
        (source / name).write_bytes(b"synthetic image manifest test\n")
        parts.append(name.encode() + b"\0" + (source / name).read_bytes())
    source_sha = digest(b"\0".join(parts))
    (image_root / "artifacts").mkdir()
    (image_root / "artifacts/p0-06-image.json").write_text(
        json.dumps(
            {
                "image_id": "sha256:" + "a" * 64,
                "source_sha256": source_sha,
                "base_digest": (
                    "python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
                ),
            }
        )
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
        image_id="sha256:" + "a" * 64,
        image_source_sha256=source_sha,
    )
    yield store, fence, saved, plan, baseline, candidate, image_root
    fence.close()
    store.close()


def handles(ctx):
    return dict(baseline=ctx[4], candidate=ctx[5], image_root=ctx[6])


def reserve(ctx, saved=None, plan=None, role="verification"):
    store, fence, original, original_plan, *_ = ctx
    return store.reserve_comparison(
        plan or original_plan, role=role, **cas(saved or original, fence), **handles(ctx)
    )


def item_for(plan, index, outcome="pass"):
    snapshot = plan.baseline if index < 2 else plan.candidate
    steps = []
    for name in STEPS:
        code = "ok"
        if name in ("valid_one", "valid_zero", "valid_negative"):
            if index == 0:
                code = "count_type"
            elif index == 2 and outcome == "reject":
                code = "count_value"
        steps.append(
            OracleStep(name=name, status="passed" if code == "ok" else "failed", code=code)
        )
    report = OracleReport(
        attempt_id=plan.attempts[index],
        snapshot_id=snapshot.snapshot_id,
        snapshot_tree_sha256=snapshot.tree_sha256,
        snapshot_file_sha256=snapshot.file_sha256,
        suite_sha256=plan.suite_sha256,
        oracle_sha256=plan.oracle_sha256,
        image_id=plan.image_id,
        image_source_sha256=plan.image_source_sha256,
        scenario="wrong_type" if index % 2 == 0 else "pass",
        steps=steps,
        status="passed" if all(s.status == "passed" for s in steps) else "failed",
        snapshot_verified_before=True,
        snapshot_verified_after=True,
        cleanup="removed",
    )
    return SlotResult(slot=SLOTS[index], report=report)


def save_all(ctx, pending, outcome="pass"):
    store, fence, _, plan, *_ = ctx
    cursor = pending
    for index in range(4):
        cursor = store.save_slot(
            pending.claim, item_for(plan, index, outcome), **cas(cursor, fence)
        )
    return cursor


def test_admit_four_ids_once_atomic_then_verified_from_saved_results(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    assert pending.claim and pending.task.usage.tool_calls == 2
    identities = store.admitted_attempts(plan.task_id, plan.request_id)
    assert tuple(item.attempt_id for item in identities) == plan.attempts
    assert all(item.status == "admitted" for item in identities)
    duplicate = reserve(ctx)
    assert duplicate.claim is None and duplicate.task.revision == pending.task.revision
    cursor = save_all(ctx, pending)
    final = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert final.task.outcome == "candidate_verified" and final.comparison.report.accepted is False
    assert len(final.comparison.results) == 4
    assert store.comparison(plan.task_id, plan.comparison_id) == final.comparison
    assert store.comparisons(plan.task_id) == [final.comparison]
    assert reserve(ctx).claim is None
    with pytest.raises(StoreError, match="repair_finished"):
        store.finalize_comparison(pending.claim, **cas(final, fence), **handles(ctx))


def test_reject_returns_ready_but_candidate_cannot_be_compared_twice(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    cursor = save_all(ctx, pending, "reject")
    final = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert final.task.phase == "ready" and final.task.outcome is None
    assert final.comparison.report.outcome == "rejected"
    new = plan.model_copy(
        update={
            "request_id": uid(),
            "comparison_id": uid(),
            "attempts": tuple(uid() for _ in range(4)),
        }
    )
    with pytest.raises(StoreError, match="comparison_conflict"):
        reserve(ctx, saved=final, plan=new)
    assert store.get(plan.task_id).task.usage.tool_calls == 2


@pytest.mark.parametrize("role", ["repair", "diagnosis", "single"])
def test_only_verification_in_multi_mode(ctx, role):
    with pytest.raises(StoreError, match="permission_denied"):
        reserve(ctx, role=role)


@pytest.mark.parametrize("field", ["request_id", "comparison_id", "attempts", "candidate"])
def test_duplicate_conflicts_without_execution_grant(ctx, field):
    pending = reserve(ctx)
    plan = ctx[3]
    changed = {
        field: uid()
        if field in ("request_id", "comparison_id")
        else (
            tuple(uid() for _ in range(4))
            if field == "attempts"
            else plan.candidate.model_copy(update={"file_sha256": "0" * 64})
        )
    }
    with pytest.raises(StoreError):
        reserve(ctx, saved=pending, plan=plan.model_copy(update=changed))


def test_strict_prefix_claim_and_cas_then_idempotent_save(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    with pytest.raises(StoreError, match="slot_conflict"):
        store.save_slot(pending.claim, item_for(plan, 1), **cas(pending, fence))
    fake = RepairClaim(plan.task_id, plan.request_id, "different token")
    with pytest.raises(StoreError, match="claim_conflict"):
        store.save_slot(fake, item_for(plan, 0), **cas(pending, fence))
    saved = store.save_slot(pending.claim, item_for(plan, 0), **cas(pending, fence))
    repeated = store.save_slot(pending.claim, item_for(plan, 0), **cas(pending, fence))
    assert saved.task.revision == repeated.task.revision and repeated.claim is None
    with pytest.raises(StoreError, match="stale_version"):
        store.save_slot(pending.claim, item_for(plan, 1), **cas(pending, fence))
    changed = item_for(plan, 0)
    changed.report.frames = 20
    with pytest.raises(StoreError, match="slot_conflict"):
        store.save_slot(pending.claim, changed, **cas(saved, fence))


@pytest.mark.parametrize(
    "field",
    [
        "attempt_id",
        "snapshot_id",
        "snapshot_file_sha256",
        "suite_sha256",
        "oracle_sha256",
        "image_id",
    ],
)
def test_result_identity_and_version_cannot_be_substituted(ctx, field):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    item = item_for(plan, 0)
    setattr(
        item.report,
        field,
        uid()
        if field in ("attempt_id", "snapshot_id")
        else ("sha256:" + "0" * 64 if field == "image_id" else "0" * 64),
    )
    with pytest.raises(StoreError, match="attempt_binding"):
        store.save_slot(pending.claim, item, **cas(pending, fence))
    assert store.get_comparison(plan.task_id, plan.request_id).results == ()


def test_partial_results_never_pass_and_preserve_all_identities(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    cursor = store.save_slot(pending.claim, item_for(plan, 0), **cas(pending, fence))
    final = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert final.task.outcome == "inconclusive"
    assert len(store.admitted_attempts(plan.task_id, plan.request_id)) == 4


@pytest.mark.parametrize("status", ["inconclusive", "cancelled", "outcome_unknown"])
def test_failure_stops_further_slots(ctx, status):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    item = item_for(plan, 0)
    item.report.status = status
    item.report.cleanup = "unconfirmed" if status == "outcome_unknown" else "removed"
    saved = store.save_slot(pending.claim, item, **cas(pending, fence))
    with pytest.raises(StoreError, match="comparison_stopped"):
        store.save_slot(pending.claim, item_for(plan, 1), **cas(saved, fence))
    final = store.finalize_comparison(pending.claim, **cas(saved, fence), **handles(ctx))
    assert final.task.outcome in ("inconclusive", "cancelled", "outcome_unknown")


def test_slot_and_finalize_transactions_roll_back_on_event_failure(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    with sqlite3.connect(store._base.path) as db:
        db.execute(
            "CREATE TRIGGER fail BEFORE INSERT ON repair_events "
            "BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
    with pytest.raises(StoreError, match="store_unavailable"):
        store.save_slot(pending.claim, item_for(plan, 0), **cas(pending, fence))
    assert store.get_comparison(plan.task_id, plan.request_id).results == ()
    assert all(
        a.status == "admitted" for a in store.admitted_attempts(plan.task_id, plan.request_id)
    )


def test_candidate_or_image_tamper_blocks_finalize_and_fresh_verified_label(ctx):
    store, fence, _, plan, _, candidate, image_root = ctx
    pending = reserve(ctx)
    cursor = save_all(ctx, pending)
    final = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert (
        store.read_verified_comparison(plan.task_id, plan.request_id, **handles(ctx))
        == final.comparison
    )
    (image_root / "containers/p0_06/supervisor.py").write_text("changed")
    with pytest.raises(StoreError, match="version_mismatch"):
        store.read_verified_comparison(plan.task_id, plan.request_id, **handles(ctx))
    assert (
        store.get_comparison(plan.task_id, plan.request_id).report.outcome == "candidate_verified"
    )
    # Historical metadata is immutable; replay still grants nothing after integrity changes.
    assert reserve(ctx).claim is None


def test_version_changed_after_four_results_cannot_be_verified(ctx):
    store, fence, _, _, _, candidate, _ = ctx
    pending = reserve(ctx)
    cursor = save_all(ctx, pending)
    source = candidate.root / "server.py"
    source.chmod(0o644)
    source.write_text("changed")
    source.chmod(0o444)
    final = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert final.task.outcome == "inconclusive"
    assert final.comparison.report.reason == "version_mismatch"


def test_unknown_recovery_does_not_finalize_or_restart_four_completed_results(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    cursor = save_all(ctx, pending)
    with pytest.raises(StoreError, match="repair_busy"):
        store.reconcile_comparison(
            plan.task_id, expected_revision=cursor.task.revision, expected_sha256=cursor.task_sha256
        )
    fence.close()
    recovered = store.reconcile_comparison(
        plan.task_id, expected_revision=cursor.task.revision, expected_sha256=cursor.task_sha256
    )
    assert recovered.task.outcome == "outcome_unknown" and recovered.comparison.report is None
    assert len(recovered.comparison.results) == 4
    with RepairFence(store.directory, plan.task_id) as owner:
        replay = store.reserve_comparison(
            plan, role="verification", **cas(recovered, owner), **handles(ctx)
        )
        assert replay.claim is None
        with pytest.raises(StoreError, match="repair_finished"):
            store.finalize_comparison(pending.claim, **cas(recovered, owner), **handles(ctx))


@pytest.mark.parametrize("table", [repair_comparisons, repair_comparison_attempts])
def test_comparison_or_attempt_tamper_rejected_by_base_reader(ctx, table):
    store, _, _, plan, *_ = ctx
    reserve(ctx)
    with store._base._transaction(write=True) as db:
        if table is repair_comparisons:
            db.execute(update(table).values(sha256="0" * 64))
        else:
            db.execute(update(table).where(table.c.slot_index == 0).values(attempt_id=uid()))
    with pytest.raises(StoreError, match="store_corrupt"):
        store.get(plan.task_id)


def test_compare_callback_advances_cas_before_finalize(ctx, monkeypatch):
    import importlib

    module = importlib.import_module("agent_workbench.candidate_execution.compare")
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    cursor = pending
    seen = []

    async def fake_oracle(_snapshot, **kwargs):
        index = plan.attempts.index(kwargs["attempt_id"])
        seen.append(index)
        return item_for(plan, index).report

    async def save(item):
        nonlocal cursor
        cursor = store.save_slot(pending.claim, item, **cas(cursor, fence))

    monkeypatch.setattr(module, "run_oracle", fake_oracle)
    asyncio.run(
        compare(
            plan,
            ctx[4],
            ctx[5],
            image_root=ctx[6],
            save_result=save,
            remaining_seconds=lambda: 100.0,
        )
    )
    assert seen == [0, 1, 2, 3] and cursor.task.revision == pending.task.revision + 4
    final = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert final.task.outcome == "candidate_verified"


def test_v4_upgrade_preserves_old_dtos_and_pending_candidate(ctx):
    store, fence, saved, plan, *_ = ctx
    with store._base._transaction(write=True) as db:
        command.downgrade(store._base._migration(db), "0004_repairs")
    names = ("repair_tasks", "repair_requests", "repair_candidates", "repair_events")
    with sqlite3.connect(store._base.path) as db:
        before = {n: db.execute(f"SELECT * FROM {n} ORDER BY 1").fetchall() for n in names}
    with pytest.raises(StoreError, match="schema_incompatible"):
        store.get(plan.task_id)
    store.initialize()
    with sqlite3.connect(store._base.path) as db:
        assert before == {n: db.execute(f"SELECT * FROM {n} ORDER BY 1").fetchall() for n in names}
    assert store.get(plan.task_id).task == saved.task
    with pytest.raises(StoreError, match="invalid_repair_input"):
        store.finish_task(plan.task_id, "candidate_verified", **cas(saved, fence))


def test_second_candidate_has_new_comparison_and_identities(ctx):
    store, fence, _, plan, baseline, _, _ = ctx
    pending = reserve(ctx)
    cursor = save_all(ctx, pending, "reject")
    rejected = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    patch = CandidatePatch(
        expected_baseline_hash=baseline.ref.tree_sha256,
        expected_file_hash=baseline.ref.file_sha256,
        replacement=(
            "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
            '    return {"count": count}\n'
        ),
    )
    claim = store.reserve_candidate(
        plan.task_id, uid(), uid(), "repair", patch, **cas(rejected, fence)
    )
    candidate = SnapshotStore(baseline.root.parent).create_candidate(
        baseline, claim.candidate.candidate_id, patch
    )
    committed = store.finish_candidate(claim.claim, snapshot=candidate.ref, **cas(claim, fence))
    next_plan = plan.model_copy(
        update={
            "request_id": uid(),
            "comparison_id": uid(),
            "candidate": candidate.ref,
            "attempts": tuple(uid() for _ in range(4)),
        }
    )
    second = store.reserve_comparison(
        next_plan,
        role="verification",
        **cas(committed, fence),
        baseline=baseline,
        candidate=candidate,
        image_root=ctx[6],
    )
    assert second.claim and second.task.candidate_count == 2 and second.task.usage.tool_calls == 4
    assert len(store.comparisons(plan.task_id)) == 2


@pytest.mark.parametrize("ctx", ["single_role"], indirect=True)
def test_single_role_comparison_uses_same_admission(ctx):
    pending = reserve(ctx, role="single")
    assert pending.claim and pending.task.usage.tool_calls == 2
    with pytest.raises(StoreError, match="permission_denied"):
        reserve(ctx, saved=pending, role="verification")


@pytest.mark.parametrize("field", ["suite_sha256", "oracle_sha256", "image_source_sha256"])
def test_unverified_versions_fail_before_any_identity_or_budget(ctx, field):
    store, _, saved, plan, *_ = ctx
    invalid = plan.model_copy(update={field: "0" * 64})
    with pytest.raises(StoreError, match="version_mismatch"):
        reserve(ctx, plan=invalid)
    assert store.get(plan.task_id).task == saved.task and store.comparisons(plan.task_id) == []
