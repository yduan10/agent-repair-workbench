import asyncio

import pytest

from agent_workbench.repair_runtime.controller import RepairController
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.schema import web_repair_requests
from agent_workbench.web_repairs.fencing import RepairWebFence
from agent_workbench.web_repairs.recovery import WebRepairRecovery
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_repair_recovery import FakeDocker
from tests.test_web_repair_execution import run
from tests.test_web_repair_execution import web as web


def test_last_inspect_receipt_cas(web):
    w = web.setup()
    run(w)
    service = WebRepairRecovery(w.store, w.ctx.image, FakeDocker())
    original = service.inspect
    count = 0

    async def inspect(controller):
        nonlocal count
        count += 1
        result = await original(controller)
        # 5 preflight, 5 apply inspection, then post-evidence inspection.
        if count == 11:
            with w.store._base._transaction(write=True) as db:
                db.execute(web_repair_requests.update().values(cancel_requested=1))
        return result

    service.inspect = inspect
    result = asyncio.run(
        service.release_checked(w.request.request_id, owner=w.owner, fence=w.fence, apply=True)
    )
    assert count == 15
    assert not result.released and w.store.receipt(w.request.request_id).active


def test_cancel_recovery_keeps_slot_and_owner_during_cleanup(web):
    w = web.setup()
    run(w)
    service = WebRepairRecovery(w.store, w.ctx.image, FakeDocker())
    started = asyncio.Event()
    checked = []

    async def inspect(controller):
        started.set()
        try:
            await asyncio.sleep(20)
        finally:
            for owner in (
                RepairWebFence(w.store.directory),
                RepairFence(w.store.directory, w.request.request_id),
            ):
                with pytest.raises(StoreError):
                    owner.acquire()
                checked.append(True)

    service.inspect = inspect

    async def drive():
        task = asyncio.create_task(
            service.release_checked(w.request.request_id, owner=w.owner, fence=w.fence, apply=True)
        )
        await started.wait()
        task.cancel()
        return await task

    result = asyncio.run(drive())
    assert checked == [True, True]
    assert not result.released and w.store.receipt(w.request.request_id).active


def test_historical_claim_rebuilt_controller_cannot_rerun(web):
    w = web.setup()
    runtime = w.runtime
    run(w)
    w.runtime = RepairController(
        store=w.store,
        snapshots=runtime.snapshots,
        baseline=runtime.baseline,
        registry=runtime.registry,
        adapter=w.adapter,
        mode=runtime.mode,
        image_root=w.ctx.image,
    )
    with pytest.raises(StoreError):
        run(w)
    assert w.adapter.calls == 4
