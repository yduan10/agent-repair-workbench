"""Independent B3c counterexamples: real durable store, synthetic host oracle."""

import asyncio

from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.orchestration.contracts import EvidenceRef
from agent_workbench.run_store.models import StoreError
from tests.agents.test_repair_tool_bridge import (
    apply,
    apply_request,
    compare_request,
    invoke,
    reproduce,
    reproduce_request,
)

pytest_plugins = ("tests.agents.test_repair_tool_bridge",)


def test_candidate_published_but_db_commit_fails_cannot_publish_twice(ctx, monkeypatch):
    reproduce(ctx)
    request = apply_request(ctx)
    published = []
    original = ctx.snapshots.create_candidate

    def create(*args):
        result = original(*args)
        published.append(result.ref)
        return result

    def fail(*args, **kwargs):
        raise StoreError("store_busy")

    monkeypatch.setattr(ctx.snapshots, "create_candidate", create)
    monkeypatch.setattr(ctx.store, "finish_candidate", fail)
    result = invoke(ctx, "repair", request)
    assert result.response.error_code == "RESULT_UNKNOWN" and result.requires_reconcile
    assert len(published) == 1
    assert (ctx.baseline.root.parent / request.candidate_id / "server.py").is_file()
    assert ctx.store.candidates(ctx.task_id)[0].status == "preparing"
    try:
        invoke(ctx, "repair", request)
    except ResourceError:
        pass
    else:
        raise AssertionError("unknown bridge must stop")
    assert len(published) == 1


def test_comparison_tree_mismatch_does_not_reserve_or_execute(ctx):
    reproduce(ctx)
    candidate = apply(ctx)
    request = compare_request(ctx, candidate).model_copy(
        update={"expected_candidate_tree_hash": "f" * 64}
    )
    before = ctx.cursor.task.usage.tool_calls
    result = invoke(ctx, "verification", request)
    assert result.response.error_code == "STALE_VERSION"
    assert result.cursor.task.usage.tool_calls == before
    assert len(ctx.attempts) == 1
    assert ctx.store.comparisons(ctx.task_id) == []


def test_authorized_evidence_id_with_wrong_hash_is_not_authorized(ctx):
    reproduce(ctx)
    known = ctx.registry.task_spec().evidence[-1]
    forged = EvidenceRef(evidence_id=known.evidence_id, sha256="f" * 64)
    result = invoke(ctx, "repair", apply_request(ctx, evidence_refs=(forged,)))
    assert result.response.error_code == "PERMISSION_DENIED"
    assert ctx.store.candidates(ctx.task_id) == []


def test_reproduction_frozen_image_changes_after_admission_never_unlocks_patch(ctx):
    async def mutate_image():
        (ctx.image / "containers/p0_06/supervisor.py").write_text("changed after admission")

    ctx.oracle_hook = mutate_image
    result = invoke(ctx, "diagnosis", reproduce_request(ctx))
    assert result.response.status != "ok"
    assert result.cursor.task.outcome == "inconclusive"
    after = invoke(ctx, "repair", apply_request(ctx))
    assert after.response.error_code == "PERMISSION_DENIED"
    assert len(ctx.attempts) == 1
    assert ctx.store.candidates(ctx.task_id) == []


def test_no_task_lingers_after_repeated_cancellation_of_t04(ctx, monkeypatch):
    from agent_workbench.controlled_tools import runtime as readonly

    cleaned = []
    original = readonly.ToolRuntime.execute

    async def slow(self, role, request, **kwargs):
        if request.tool != "check_contract":
            return await original(self, role, request, **kwargs)
        try:
            await asyncio.sleep(30)
        finally:
            cleaned.append(True)

    monkeypatch.setattr(readonly.ToolRuntime, "execute", slow)
    request = next(r for r in ctx.registry.templates("diagnosis") if r.tool == "check_contract")

    async def run():
        task = asyncio.create_task(ctx.bridge.execute("diagnosis", request, cursor=ctx.cursor))
        while ctx.store.get(ctx.task_id).task.phase != "tool_pending":
            await asyncio.sleep(0)
        task.cancel()
        task.cancel()
        result = await task
        assert result.cancelled
        assert result.response.error_code == "RESULT_UNKNOWN"
        assert result.cursor.task.phase == "finished"
        assert result.cursor.task.outcome == "outcome_unknown"
        assert cleaned == [True]
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())
