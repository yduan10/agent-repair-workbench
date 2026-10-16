"""Independent B2 adversarial checks; no live model, Docker or user database."""

import asyncio
import threading
from uuid import uuid4

import pytest

from agent_workbench.run_store.models import StoreError
from agent_workbench.web_repairs import catalog
from agent_workbench.web_repairs.fencing import RepairWebFence
from agent_workbench.web_repairs.models import RepairRequest
from agent_workbench.web_repairs.store import WebRepairStore
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_web_repair_api import (
    anyio_backend as anyio_backend,
)
from tests.test_web_repair_api import (
    drained,
    request,
)
from tests.test_web_repair_api import (
    host as host,
)


@pytest.mark.anyio
async def test_cancelled_reader_holds_capacity_until_sql_thread_finishes(host, monkeypatch):
    service, _ = host
    entered = threading.Event()
    release = threading.Event()
    original = WebRepairStore.receipt

    def blocked(self, task_id):
        entered.set()
        assert release.wait(5)
        return original(self, task_id)

    monkeypatch.setattr(WebRepairStore, "receipt", blocked)
    first = asyncio.create_task(service.read(str(uuid4())))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        first.cancel()
        await asyncio.sleep(0.03)
        assert not first.done()
        second = asyncio.create_task(service.read(str(uuid4())))
        await asyncio.sleep(0.03)
        assert (await service.read(str(uuid4()))).body == {"error": "repair_reads_busy"}
    finally:
        release.set()
        await first
        if "second" in locals():
            await second
    assert not service.reads.locked()
    await service.close()


@pytest.mark.anyio
async def test_shutdown_during_preflight_never_creates_receipt(host, monkeypatch):
    service, model = host
    entered, release = asyncio.Event(), asyncio.Event()

    async def preflight(root):
        entered.set()
        await release.wait()

    monkeypatch.setattr(catalog, "preflight", preflight)
    data = RepairRequest(**request())
    submitted = asyncio.create_task(service.submit(data))
    await entered.wait()
    closing = asyncio.create_task(service.close())
    await asyncio.sleep(0)
    assert service.stopping and not closing.done()
    closing.cancel()
    await asyncio.sleep(0)
    assert not closing.done()
    with pytest.raises(StoreError, match="repair_busy"):
        with RepairWebFence(service.directory):
            pass
    release.set()
    assert (await submitted).body == {"error": "service_stopping"}
    await closing
    assert not service.tasks and not model.calls
    assert (await service.read(data.request_id)).status == 404
    with RepairWebFence(service.directory):
        pass


@pytest.mark.anyio
async def test_preflight_failure_is_sanitized_and_owner_reusable(host, monkeypatch):
    service, model = host

    async def broken(root):
        raise RuntimeError("SECRET private key and path")

    monkeypatch.setattr(catalog, "preflight", broken)
    result = await service.submit(RepairRequest(**request()))
    await drained(service)
    assert result.status == 503 and result.body == {"error": "store_unavailable"}
    assert not model.calls and not service.active_ids
    with RepairWebFence(service.directory):
        pass
    await service.close()


@pytest.mark.anyio
async def test_duplicate_does_not_use_new_adapter_or_preflight(host, monkeypatch):
    service, model = host
    data = RepairRequest(**request())
    assert (await service.submit(data)).status == 202
    await drained(service)

    def forbidden(*args, **kwargs):
        pytest.fail("historical request must not evaluate new runtime configuration")

    service.config_loader = forbidden
    service.adapter_factory = forbidden
    monkeypatch.setattr(catalog, "preflight", forbidden)
    assert (await service.submit(data)).status == 200
    assert model.calls == 1
    await service.close()


@pytest.mark.anyio
async def test_read_and_cancel_missing_id_do_not_admit(host):
    service, model = host
    data = RepairRequest(**request())
    assert (await service.read(data.request_id, cancel=True)).status == 404
    assert (await service.read(data.request_id)).status == 404
    assert not service.tasks and not service.active_ids and not model.calls
    store = WebRepairStore(service.directory)
    try:
        assert store.active_id() is None
        assert store.existing(data) is None
    finally:
        store.close()
    await service.close()


@pytest.mark.anyio
async def test_duplicate_retry_after_disconnect_is_not_second_execution(host, monkeypatch):
    service, model = host
    entered, release = asyncio.Event(), asyncio.Event()

    async def preflight(root):
        entered.set()
        await release.wait()

    monkeypatch.setattr(catalog, "preflight", preflight)
    data = RepairRequest(**request())
    waiter = asyncio.create_task(service.submit(data))
    await entered.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    duplicate = await service.submit(data)
    assert duplicate.status == 429
    assert not model.calls
    release.set()
    await drained(service)
    assert (await service.submit(data)).status == 200
    assert model.calls == 1
    await service.close()


@pytest.mark.anyio
async def test_cli_only_task_cannot_be_cancelled_through_web_receipt(host, ctx):
    service, model = host
    before = ctx.store.get(ctx.task_id)
    result = await service.read(ctx.task_id, cancel=True)
    assert result.status == 404
    assert ctx.store.get(ctx.task_id) == before
    assert not model.calls
    await service.close()


@pytest.mark.anyio
async def test_catalog_does_not_connect_docker_or_execute_adapter(host, monkeypatch):
    service, model = host

    async def forbidden(*args, **kwargs):
        pytest.fail("GET catalog must not contact execution dependencies")

    monkeypatch.setattr(catalog.DockerControl, "connect", forbidden)
    monkeypatch.setattr(catalog, "preflight", forbidden)
    result = await service.catalog()
    assert result.status == 200
    assert result.body["slot"] == {"status": "available", "task_id": None}
    assert not service.tasks and not model.calls
    await service.close()
