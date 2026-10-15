"""Independent B3d counterexamples; real temporary ledger, synthetic adapters only."""

import asyncio

import pytest

from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.run_store.models import StoreError
from tests.agents.test_repair_controller import controller, execute
from tests.agents.test_repair_tool_bridge import ctx as ctx


def test_owner_fence_covers_model_and_every_oracle(ctx):
    runtime, adapter = controller(
        ctx, ["request_reproduction", "apply_candidate", "compare_candidate"]
    )
    observed = []

    async def assert_owned():
        task_id = runtime.cursor.task.task_id
        with pytest.raises(StoreError, match="repair_busy"):
            with RepairFence(ctx.store.directory, task_id):
                pass
        observed.append(task_id)

    adapter.hook = assert_owned
    ctx.oracle_hook = assert_owned
    result = execute(runtime)
    assert result.cursor.task.outcome == "candidate_verified"
    assert len(observed) == 8  # Three models plus T05 and four T07 execution slots.
    with RepairFence(ctx.store.directory, result.cursor.task.task_id):
        pass


def test_reservation_commit_lost_ack_never_sends(ctx, monkeypatch):
    runtime, adapter = controller(ctx, ["needs_evidence"])
    original = ctx.store.reserve_model

    def fail_after_commit(*args, **kwargs):
        original(*args, **kwargs)
        raise StoreError("store_unavailable")

    monkeypatch.setattr(ctx.store, "reserve_model", fail_after_commit)
    result = execute(runtime)
    actual = ctx.store.get(result.cursor.task.task_id)
    assert result.requires_reconcile and result.cursor.task.phase == "ready"
    assert actual.task.phase == "model_pending" and actual.task.usage.model_calls == 1
    assert adapter.calls == 0 and not ctx.attempts


def test_settlement_commit_lost_ack_never_runs_tool(ctx, monkeypatch):
    runtime, adapter = controller(ctx, ["request_reproduction"])
    original = ctx.store.settle_model

    def fail_after_commit(*args, **kwargs):
        original(*args, **kwargs)
        raise StoreError("store_unavailable")

    monkeypatch.setattr(ctx.store, "settle_model", fail_after_commit)
    result = execute(runtime)
    actual = ctx.store.get(result.cursor.task.task_id)
    assert result.requires_reconcile and result.cursor.task.phase == "model_pending"
    assert actual.task.phase == "ready" and actual.task.usage.known_input_tokens == 100
    assert adapter.calls == 1 and not ctx.attempts


def test_cancel_after_settlement_never_starts_proposed_tool(ctx, monkeypatch):
    runtime, adapter = controller(ctx, ["request_reproduction"])
    original = ctx.store.settle_model

    def cancel_after_commit(*args, **kwargs):
        result = original(*args, **kwargs)
        asyncio.current_task().cancel()
        return result

    monkeypatch.setattr(ctx.store, "settle_model", cancel_after_commit)
    result = execute(runtime)
    assert result.cancelled
    assert adapter.calls == 1 and not ctx.attempts
    assert result.cursor.task.usage.tool_calls == 0


def test_cancel_after_reservation_never_enters_adapter_send(ctx, monkeypatch):
    runtime, adapter = controller(ctx, ["needs_evidence"])
    original = ctx.store.reserve_model

    def cancel_after_commit(*args, **kwargs):
        result = original(*args, **kwargs)
        asyncio.current_task().cancel()
        return result

    monkeypatch.setattr(ctx.store, "reserve_model", cancel_after_commit)
    result = execute(runtime)
    assert result.cancelled
    assert adapter.calls == 0
    assert not ctx.attempts


def test_native_repeated_cancel_holds_fence_until_sender_closes(ctx):
    runtime, adapter = controller(ctx, ["needs_evidence"])

    async def exercise():
        entered = asyncio.Event()
        cleaning = asyncio.Event()
        closed = asyncio.Event()
        release = asyncio.Event()

        async def slow_sender():
            import anyio

            entered.set()
            try:
                await asyncio.sleep(30)
            finally:
                with anyio.CancelScope(shield=True):
                    cleaning.set()
                    await release.wait()
                    closed.set()

        adapter.hook = slow_sender
        task = asyncio.create_task(runtime.run())
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 3)
        task.cancel()
        with pytest.raises(StoreError, match="repair_busy"):
            with RepairFence(ctx.store.directory, runtime.cursor.task.task_id):
                pass
        assert not task.done() and not closed.is_set()
        release.set()
        result = await asyncio.wait_for(task, 3)
        assert closed.is_set()
        return result

    result = asyncio.run(exercise())
    assert result.cancelled and adapter.calls == 1
    assert result.cursor.task.outcome == "outcome_unknown"
    with RepairFence(ctx.store.directory, result.cursor.task.task_id):
        pass


def test_deadline_after_reservation_is_not_reported_as_user_cancellation(ctx):
    runtime, adapter = controller(ctx, ["needs_evidence"])
    times = iter([0.0, 0.0, 601.0])
    runtime.clock = lambda: next(times)
    result = execute(runtime)
    assert adapter.calls == 0 and not ctx.attempts
    assert not result.cancelled
    assert result.cursor.task.outcome == "outcome_unknown"
    assert result.cursor.task.usage.reserved_tokens == 18192
