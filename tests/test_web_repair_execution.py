"""B1b: real ledger/snapshots; scripted model and synthetic, bound oracle evidence."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution import compare as compare_module
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.controlled_tools.resources import load_repair_case
from agent_workbench.repair_runtime import tools as tools_module
from agent_workbench.repair_runtime.controller import RepairController
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairTask
from agent_workbench.run_store.models import StoreError
from agent_workbench.web_repairs.fencing import RepairWebFence
from agent_workbench.web_repairs.models import WEB_BUDGET, RepairRequest
from agent_workbench.web_repairs.policy import policy_sha256
from agent_workbench.web_repairs.recovery import WebRepairRecovery
from agent_workbench.web_repairs.store import WebRepairStore
from tests.agents.test_repair_controller import Scripted
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_repair_recovery import FakeDocker, item


def uid():
    return str(uuid4())


@pytest.fixture
def web(ctx, monkeypatch):
    clock = [datetime.now(UTC).timestamp()]
    store = WebRepairStore(ctx.store.directory, clock=lambda: clock[0])
    snapshots = SnapshotStore(store.directory / "repair-snapshots")
    state = SimpleNamespace(store=store, clock=clock, ctx=ctx, snapshots=snapshots)

    def setup(case="output_mismatch", mode="three_role", script=None):
        baseline = snapshots.create_baseline(uid(), case_id=case)
        request = RepairRequest(request_id=uid(), case_id=case, mode=mode)
        owner, fence = (
            RepairWebFence(store.directory),
            RepairFence(store.directory, request.request_id),
        )
        owner.acquire()
        fence.acquire()
        state.owner, state.fence, state.request = owner, fence, request
        registry = load_repair_case(case, task_id=request.request_id, budget=WEB_BUDGET)
        initial = RepairTask(
            task_id=request.request_id,
            mode=mode,
            baseline=baseline.ref,
            started_at=datetime.now(UTC),
            budget=WEB_BUDGET,
            model_config_sha256="a" * 64,
        )
        state.admission = store.admit(
            request, initial, policy_sha256=policy_sha256(), owner=owner, task_fence=fence
        )
        state.adapter = Scripted(
            ctx,
            script
            or ["request_reproduction", "read_source", "apply_candidate", "compare_candidate"],
        )
        state.runtime = RepairController(
            store=store,
            snapshots=snapshots,
            baseline=baseline,
            registry=registry,
            adapter=state.adapter,
            mode=mode,
            image_root=ctx.image,
        )
        return state

    async def oracle(snapshot, **kwargs):
        report = await ctx.oracle(snapshot, **kwargs)
        if snapshot.ref.manifest_sha256 != ctx.baseline.ref.manifest_sha256:
            for step in report.steps:
                if step.code == "count_type":
                    step.code = "count_value"
        return report

    monkeypatch.setattr(tools_module, "run_oracle", oracle)
    monkeypatch.setattr(compare_module, "run_oracle", oracle)
    state.setup = setup
    yield state
    if hasattr(state, "owner"):
        state.fence.close()
        state.owner.close()
    store.close()


def run(w):
    return asyncio.run(w.runtime.run_created(w.admission.claim, w.admission.saved, w.fence))


def release(w, fake=None, apply=True):
    return asyncio.run(
        WebRepairRecovery(w.store, w.ctx.image, fake or FakeDocker()).release_checked(
            w.request.request_id, owner=w.owner, fence=w.fence, apply=apply
        )
    )


@pytest.mark.parametrize("case", ["output_mismatch", "counter_offset"])
@pytest.mark.parametrize("mode", ["single_role", "three_role"])
def test_four_flows_shared_loop_and_safe_release(web, case, mode):
    w = web.setup(case, mode)
    result = run(w)
    assert result.cursor.task.outcome == "candidate_verified"
    assert w.adapter.calls == 4 and len(w.ctx.attempts) == 5
    assert not result.requires_reconcile and w.store.receipt(w.request.request_id).active
    inspected = release(w, apply=False)
    assert not inspected.released and w.store.receipt(w.request.request_id).active
    released = release(w)
    assert released.released
    assert not w.store.receipt(w.request.request_id).active
    assert w.store.get(w.request.request_id).task == result.cursor.task
    with pytest.raises(StoreError):
        run(w)
    assert w.adapter.calls == 4


@pytest.mark.parametrize("reason", ["cancel", "expired", "backwards", "policy", "model"])
def test_prestart_rejection_has_zero_effects(web, reason):
    w = web.setup()
    if reason == "cancel":
        w.store.request_cancel(w.request.request_id)
    elif reason == "expired":
        w.clock[0] += 601
    elif reason == "backwards":
        w.clock[0] -= 1
    elif reason == "model":
        w.adapter.config_sha256 = "b" * 64
    else:
        w.runtime.mode = "single_role"
    if reason in ("backwards", "policy", "model"):
        with pytest.raises(StoreError):
            run(w)
    else:
        result = run(w)
        assert result.cursor.task.outcome == (
            "cancelled" if reason == "cancel" else "budget_exceeded"
        )
        assert release(w).released
    assert w.adapter.calls == 0 and not w.ctx.attempts


def test_admission_delay_reduces_budget(web):
    w = web.setup(script=["needs_evidence"])
    w.clock[0] += 590
    timeouts = []
    original = w.adapter.send

    async def send(prepared, timeout):
        timeouts.append(timeout)
        return await original(prepared, timeout)

    w.adapter.send = send
    run(w)
    assert 0 < timeouts[0] <= 10


def test_cancel_after_known_reply_keeps_usage(web):
    w = web.setup()

    async def hook():
        w.store.request_cancel(w.request.request_id)

    w.adapter.hook = hook
    result = run(w)
    assert result.cancelled and result.cursor.task.outcome == "cancelled"
    assert result.cursor.task.usage.known_input_tokens == 100
    assert not w.ctx.attempts and release(w).released


def test_durable_cancel_interrupts_wait_and_keeps_unknown_reservation(web):
    w = web.setup()

    async def hook():
        w.store.request_cancel(w.request.request_id)
        await asyncio.sleep(20)

    w.adapter.hook = hook
    result = run(w)
    assert result.cancelled
    assert result.cursor.task.usage.model_calls == 1
    assert result.cursor.task.usage.reserved_tokens > 0
    assert not w.ctx.attempts
    before = w.store.get(w.request.request_id).task.usage
    assert release(w).released
    assert w.store.get(w.request.request_id).task.usage == before


def test_unstarted_abandoned_claim_is_retired_without_execution(web):
    w = web.setup()
    assert not release(w, apply=False).released
    assert not w.store.receipt(w.request.request_id).consumed
    assert release(w).released
    assert w.store.get(w.request.request_id).task.outcome == "outcome_unknown"
    with pytest.raises(StoreError):
        run(w)
    assert w.adapter.calls == 0


def test_missing_report_absent_is_not_proof_and_late_create_can_be_reaped(web):
    w = web.setup()

    async def lost(snapshot, **kwargs):
        raise RuntimeError("synthetic lost report")

    # Durable T05 reservation exists, but create/result is unknown.
    tools_module_original = tools_module.run_oracle
    tools_module.run_oracle = lost
    try:
        result = run(w)
    finally:
        tools_module.run_oracle = tools_module_original
    assert result.requires_reconcile
    fake = FakeDocker()
    first = release(w, fake)
    assert not first.released and first.recovery.ledger_reconciled
    assert w.store.receipt(w.request.request_id).active
    before = w.store.get(w.request.request_id)
    target = w.store.inventory(w.request.request_id).targets[0]
    fake.items["a" * 64] = item(target, w.store.directory)
    second = release(w, fake)
    assert second.released and fake.removed == ["a" * 64]
    assert w.store.get(w.request.request_id) == before


@pytest.mark.parametrize("failure", ["identity", "remove", "ledger"])
def test_release_rejects_resource_or_evidence_change(web, failure):
    w = web.setup()
    run(w)
    fake = FakeDocker()
    target = w.store.inventory(w.request.request_id).targets[0]
    fake.items["a" * 64] = item(target, w.store.directory)
    if failure == "identity":
        fake.items["a" * 64]["Config"]["Cmd"] = ["wrong"]
    elif failure == "remove":
        fake.fail_remove = True
    else:
        original = fake.command

        async def command(*args):
            if args[:3] == ("container", "rm", "--force"):
                # A receipt mutation doesn't change task revision; full evidence CAS must catch it.
                with w.store._base._transaction(write=True) as db:
                    from agent_workbench.run_store.schema import web_repair_requests

                    db.execute(web_repair_requests.update().values(cancel_requested=1))
            return await original(*args)

        fake.command = command
    result = release(w, fake)
    assert not result.released and w.store.receipt(w.request.request_id).active
    if failure == "identity":
        assert not fake.removed


def test_parent_cancel_keeps_fences_until_model_settlement(web):
    w = web.setup()
    entered, cleanup = asyncio.Event(), asyncio.Event()

    async def hook():
        entered.set()
        try:
            await asyncio.sleep(20)
        finally:
            # Even cancellation cleanup cannot acquire either execution owner.
            with pytest.raises(StoreError):
                with RepairWebFence(w.store.directory):
                    pass
            with pytest.raises(StoreError):
                with RepairFence(w.store.directory, w.request.request_id):
                    pass
            cleanup.set()

    w.adapter.hook = hook

    async def drive():
        task = asyncio.create_task(
            w.runtime.run_created(w.admission.claim, w.admission.saved, w.fence)
        )
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        return await task

    result = asyncio.run(drive())
    assert cleanup.is_set() and result.cancelled
    assert w.store.get(w.request.request_id).task.usage.reserved_tokens > 0
    assert release(w).released


def test_running_wall_clock_backwards_does_not_send_next_call(web):
    w = web.setup()

    async def hook():
        w.clock[0] -= 1

    w.adapter.hook = hook
    result = run(w)
    assert w.adapter.calls == 1 and not w.ctx.attempts
    # A backward clock also prevents timestamp-monotonic settlement: retain the reservation.
    assert result.requires_reconcile or result.cursor.task.outcome == "outcome_unknown"
    assert w.store.receipt(w.request.request_id).active


def test_pending_candidate_publication_remains_blocked(web, monkeypatch):
    w = web.setup()

    def lost(*args, **kwargs):
        raise RuntimeError("publication acknowledgement lost")

    monkeypatch.setattr(w.snapshots, "create_candidate", lost)
    result = run(w)
    assert result.requires_reconcile and len(w.ctx.attempts) == 1
    report = release(w)
    assert report.recovery.ledger_reconciled and not report.released
    assert w.store.receipt(w.request.request_id).active
    assert w.store.candidates(w.request.request_id)[0].status == "outcome_unknown"


def test_interrupted_comparison_never_assumes_remaining_slots_were_not_started(web, monkeypatch):
    w = web.setup()

    async def lost(*args, **kwargs):
        raise RuntimeError("comparison acknowledgement lost")

    monkeypatch.setattr(compare_module, "run_oracle", lost)
    result = run(w)
    assert result.requires_reconcile
    fake = FakeDocker()
    targets = w.store.inventory(w.request.request_id).targets
    assert len(targets) == 5
    # Only one of four planned T07 identities has positive creation evidence.
    fake.items["a" * 64] = item(targets[1], w.store.directory)
    report = release(w, fake)
    assert not report.released and report.recovery.ledger_reconciled
    assert w.store.receipt(w.request.request_id).active
    assert w.store.comparisons(w.request.request_id)[0].report is None


@pytest.mark.parametrize("kind", ["reproduction", "comparison"])
def test_finished_record_missing_report_is_corruption(web, kind):
    import json
    import sqlite3

    from agent_workbench.mcp_config import canonical, digest

    w = web.setup()
    run(w)
    table = "repair_reproductions" if kind == "reproduction" else "repair_comparisons"
    with sqlite3.connect(w.store._base.path) as db:
        raw = db.execute(
            f"SELECT payload FROM {table} WHERE task_id=?", (w.request.request_id,)
        ).fetchone()[0]
        value = json.loads(raw)
        value["report"] = None
        raw = canonical(value)
        db.execute(
            f"UPDATE {table} SET payload=?, sha256=? WHERE task_id=?",
            (raw, digest(raw), w.request.request_id),
        )
    fake = FakeDocker()
    assert not release(w, fake).released
    assert not fake.removed
    with sqlite3.connect(w.store._base.path) as db:
        assert db.execute("SELECT active FROM web_repair_requests").fetchone()[0] == 1


def test_final_release_cas_rejects_last_moment_receipt_change(web, monkeypatch):
    w = web.setup()
    run(w)
    original = w.store._release_cas

    def changed(task_id, stamp, **kwargs):
        from agent_workbench.run_store.schema import web_repair_requests

        with w.store._base._transaction(write=True) as db:
            db.execute(web_repair_requests.update().values(cancel_requested=1))
        return original(task_id, stamp, **kwargs)

    monkeypatch.setattr(w.store, "_release_cas", changed)
    assert not release(w).released and w.store.receipt(w.request.request_id).active


@pytest.mark.parametrize(
    "cleanup,error",
    [
        ("unconfirmed", "cleanup_unconfirmed"),
        ("removed", "attach_cleanup_unconfirmed"),
        ("not_created", "docker_failure"),
    ],
)
def test_unknown_resource_report_does_not_release_on_absent(web, monkeypatch, cleanup, error):
    w = web.setup()
    original = tools_module.run_oracle

    async def ambiguous(*args, **kwargs):
        report = await original(*args, **kwargs)
        report.status = "outcome_unknown"
        report.error, report.cleanup = error, cleanup
        return report

    monkeypatch.setattr(tools_module, "run_oracle", ambiguous)
    result = run(w)
    assert result.cursor.task.outcome == "outcome_unknown"
    assert not release(w).released and w.store.receipt(w.request.request_id).active
