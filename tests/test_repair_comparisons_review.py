"""Independent B1c SQLite transaction and identity probes; no Docker or model execution."""

import sqlite3
from datetime import UTC, datetime

import pytest

from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairTask
from agent_workbench.run_store.models import StoreError
from tests.test_repair_comparisons import cas, handles, item_for, reserve, save_all, uid
from tests.test_repair_comparisons import ctx as _ctx

ctx = _ctx


def install_failure(store):
    with sqlite3.connect(store._base.path) as db:
        db.execute(
            "CREATE TRIGGER review_failure BEFORE INSERT ON repair_events "
            "BEGIN SELECT RAISE(ABORT, 'synthetic'); END"
        )


def remove_failure(store):
    with sqlite3.connect(store._base.path) as db:
        db.execute("DROP TRIGGER review_failure")


def test_admission_rollback_removes_all_four_identities_and_budget(ctx):
    store, _, original, plan, *_ = ctx
    install_failure(store)
    with pytest.raises(StoreError, match="^store_unavailable$"):
        reserve(ctx)
    assert store.get(plan.task_id).task == original.task
    assert store.comparisons(plan.task_id) == []
    with sqlite3.connect(store._base.path) as db:
        assert db.execute("SELECT count(*) FROM repair_comparison_attempts").fetchone() == (0,)
    remove_failure(store)
    pending = reserve(ctx)
    assert pending.claim and pending.task.usage.tool_calls == original.task.usage.tool_calls + 1


def test_final_verdict_and_request_settlement_roll_back_together(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    cursor = save_all(ctx, pending)
    install_failure(store)
    with pytest.raises(StoreError, match="^store_unavailable$"):
        store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert store.get(plan.task_id).task == cursor.task
    record = store.get_comparison(plan.task_id, plan.request_id)
    assert record.status == "reserved" and record.report is None and len(record.results) == 4
    remove_failure(store)
    final = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(ctx))
    assert final.task.outcome == "candidate_verified"
    assert final.task.usage.tool_calls == cursor.task.usage.tool_calls


def test_mutated_nested_report_cannot_enter_persisted_prefix(ctx):
    store, fence, _, plan, *_ = ctx
    pending = reserve(ctx)
    malformed = item_for(plan, 0)
    malformed.report.steps.clear()
    with pytest.raises(StoreError, match="^invalid_repair_input$"):
        store.save_slot(pending.claim, malformed, **cas(pending, fence))
    assert store.get(plan.task_id).task == pending.task
    assert store.get_comparison(plan.task_id, plan.request_id).results == ()


def test_t07_identity_cannot_be_reused_by_another_task(ctx):
    store, _, _, plan, baseline, _, image_root = ctx
    reserve(ctx)
    other = RepairTask(
        task_id=uid(),
        baseline=baseline.ref,
        mode="three_role",
        started_at=datetime.now(UTC),
        budget=Budget(total_tokens=1000, output_tokens=100),
    )
    with RepairFence(store.directory, other.task_id) as owner:
        created = store.create_task(other, fence=owner)
        patch = CandidatePatch(
            expected_baseline_hash=baseline.ref.tree_sha256,
            expected_file_hash=baseline.ref.file_sha256,
            replacement="def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
            '    return {"count": count}\n',
        )
        pending = store.reserve_candidate(
            other.task_id, uid(), uid(), "repair", patch, **cas(created, owner)
        )
        candidate = SnapshotStore(baseline.root.parent).create_candidate(
            baseline, pending.candidate.candidate_id, patch
        )
        committed = store.finish_candidate(
            pending.claim, snapshot=candidate.ref, **cas(pending, owner)
        )
        reused = plan.model_copy(
            update={
                "task_id": other.task_id,
                "request_id": uid(),
                "comparison_id": uid(),
                "candidate": candidate.ref,
                "attempts": (plan.attempts[0], uid(), uid(), uid()),
            }
        )
        with pytest.raises(StoreError, match="^attempt_conflict$"):
            store.reserve_comparison(
                reused,
                role="verification",
                **cas(committed, owner),
                baseline=baseline,
                candidate=candidate,
                image_root=image_root,
            )
        assert store.get(other.task_id).task == committed.task
        assert store.comparisons(other.task_id) == []
