"""Independent B1b ledger probes; all databases and snapshots are test-owned."""

import sqlite3

import pytest

from agent_workbench.model_gateway.gateway import Reply
from agent_workbench.run_store.models import StoreError
from tests.test_repair_store import (  # noqa: F401
    cas,
    patch_for,
    reserve_candidate,
    reserve_model,
    uid,
)
from tests.test_repair_store import (
    ctx as _ctx,
)

ctx = _ctx


def test_three_role_rotation_cannot_reset_model_budget(ctx):
    store, fence, saved, *_ = ctx
    roles = ("diagnosis", "repair", "verification")
    for index in range(12):
        reserved = reserve_model(ctx, saved=saved, role=roles[index % 3])
        saved = store.settle_model(reserved.claim, Reply(None, 2, 1), **cas(reserved, fence))
    assert saved.task.usage.model_calls == 12
    assert saved.task.usage.known_input_tokens == 24
    for role in roles:
        with pytest.raises(StoreError, match="^budget_exceeded$"):
            reserve_model(ctx, saved=saved, role=role)
    assert store.get(saved.task.task_id).task == saved.task


def test_settlement_transaction_failure_does_not_consume_claim_or_lose_reservation(ctx):
    store, fence, *_ = ctx
    pending = reserve_model(ctx)
    with sqlite3.connect(store._base.path) as db:
        db.execute(
            "CREATE TRIGGER review_fail_settlement BEFORE INSERT ON repair_events "
            "BEGIN SELECT RAISE(ABORT, 'synthetic'); END"
        )
    with pytest.raises(StoreError, match="^store_unavailable$"):
        store.settle_model(pending.claim, Reply(None, 10, 5), **cas(pending, fence))
    assert store.get(pending.task.task_id).task == pending.task
    with sqlite3.connect(store._base.path) as db:
        db.execute("DROP TRIGGER review_fail_settlement")
    completed = store.settle_model(pending.claim, Reply(None, 10, 5), **cas(pending, fence))
    assert completed.task.usage.model_calls == 1
    assert completed.task.usage.reserved_tokens == 0
    assert completed.task.usage.known_input_tokens == 10
    with pytest.raises(StoreError, match="^claim_conflict$"):
        store.settle_model(pending.claim, Reply(None, 10, 5), **cas(completed, fence))


def test_published_snapshot_with_uncommitted_metadata_remains_unknown_without_replay(ctx):
    store, fence, _, snapshots, baseline, _ = ctx
    pending = reserve_candidate(ctx)
    snapshot = snapshots.create_candidate(
        baseline, pending.candidate.candidate_id, patch_for(baseline)
    )
    original = snapshots.verify(snapshot)
    fence.close()
    recovered = store.reconcile(
        pending.task.task_id,
        expected_revision=pending.task.revision,
        expected_sha256=pending.task_sha256,
    )
    assert recovered.task.outcome == "outcome_unknown"
    assert recovered.candidate.status == "outcome_unknown"
    assert recovered.candidate.snapshot is None
    assert recovered.task.candidate_count == 1
    assert recovered.task.usage.tool_calls == 1
    assert snapshots.verify(snapshot) == original
    fence.acquire()
    replay = reserve_candidate(
        ctx,
        saved=recovered,
        request=pending.request.request_id,
        candidate=pending.candidate.candidate_id,
    )
    assert replay.claim is None and replay.task == recovered.task


def test_same_request_cannot_change_role_or_cross_model_tool_operation(ctx):
    store, fence, initial, *_ = ctx
    request = uid()
    pending = reserve_model(ctx, request=request, role="diagnosis")
    with pytest.raises(StoreError, match="^request_conflict$"):
        reserve_model(ctx, saved=pending, request=request, role="repair")
    with pytest.raises(StoreError, match="^request_conflict$"):
        store.reserve_tool(
            initial.task.task_id,
            request,
            "diagnosis",
            "T01",
            "b" * 64,
            **cas(pending, fence),
        )
    assert store.get(initial.task.task_id).task == pending.task
