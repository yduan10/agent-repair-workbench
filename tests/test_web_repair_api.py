"""B2 HTTP/lifecycle with real temporary SQLite and explicitly scripted model."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_workbench import api
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.model_gateway.gateway import PreparedCall, Reply
from agent_workbench.run_store.models import StoreError
from agent_workbench.web_repairs import catalog
from agent_workbench.web_repairs.models import RepairRequest
from agent_workbench.web_repairs.service import RepairService
from agent_workbench.web_repairs.store import WebRepairStore
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_web_analysis_service import config
from tests.test_web_repair_execution import web as web

ORIGIN = {"origin": "http://127.0.0.1:3010"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def request(**updates):
    return {
        "request_id": str(uuid4()),
        "case_id": "output_mismatch",
        "mode": "three_role",
        **updates,
    }


class Model:
    config_sha256 = "a" * 64

    def __init__(self):
        self.calls = 0
        self.wait = False
        self.entered = asyncio.Event()

    def prompt(self, role):
        return "synthetic " + role

    def prepare(self, role, messages, output_cap):
        raw = canonical(messages)
        return PreparedCall(raw, digest(raw), 10000, output_cap, "b" * 64)

    async def send(self, prepared, timeout):
        self.calls += 1
        self.entered.set()
        if self.wait:
            await asyncio.sleep(30)
        return Reply(
            decision=canonical(
                {
                    "action": "conclude",
                    "disposition": "needs_evidence",
                    "reason_code": "evidence_missing",
                    "evidence_refs": [],
                }
            ),
            input_tokens=100,
            output_tokens=10,
        )


@pytest.fixture
def host(ctx, monkeypatch):
    model = Model()
    service = RepairService(
        ctx.store.directory,
        image_root=ctx.image,
        config_loader=config,
        adapter_factory=lambda _: model,
    )
    monkeypatch.setenv("AWB_STATE_DIR", str(ctx.store.directory))
    monkeypatch.delenv("AWB_FRONTEND_PORT", raising=False)
    monkeypatch.setattr(api, "RepairService", lambda _: service)

    async def prepared(root):
        return None

    monkeypatch.setattr(catalog, "preflight", prepared)
    return service, model


async def drained(service):
    async with asyncio.timeout(6):
        while service.tasks:
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("case", ["output_mismatch", "counter_offset"])
@pytest.mark.parametrize("mode", ["single_role", "three_role"])
@pytest.mark.anyio
async def test_http_accept_query_reuse_and_readonly_catalog(host, case, mode):
    service, model = host
    app = api.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://127.0.0.1", headers=ORIGIN
        ) as client,
    ):
        data = request(case_id=case, mode=mode)
        response = await client.post("/api/repair-runs", json=data)
        assert response.status_code == 202 and response.json()["reused"] is False
        assert response.headers["cache-control"] == "no-store"
        await drained(service)
        assert model.calls == 1
        result = await client.get("/api/repair-runs/" + data["request_id"])
        body = result.json()
        assert (
            result.status_code == 200 and body["task"]["phase"] == "finished" and not body["active"]
        )
        assert str(service.directory) not in json.dumps(body)
        assert not ({"claim", "token", "policy_sha256", "consumed"} & body.keys())

        def missing():
            raise RuntimeError("SECRET endpoint and key")

        service.config_loader = missing
        duplicate = await client.post("/api/repair-runs", json=data)
        assert duplicate.status_code == 200 and duplicate.json()["reused"]
        assert model.calls == 1
        catalog_result = await client.get("/api/repair-runs/catalog")
        assert catalog_result.status_code == 200
        assert catalog_result.json()["slot"]["status"] == "available"
        assert "SECRET" not in catalog_result.text
        conflict = await client.post(
            "/api/repair-runs",
            json={**data, "mode": "single_role" if mode == "three_role" else "three_role"},
        )
        assert conflict.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        None,
        request(argv=["SECRET"]),
        request(case_id="passing"),
        request(mode="four_role"),
        request(request_id="bad"),
        request(total_tokens=9999999),
    ],
)
def test_rejects_input_without_execution(host, payload):
    service, model = host
    with TestClient(api.create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/repair-runs",
            content=json.dumps(payload),
            headers={**ORIGIN, "content-type": "application/json"},
        )
        assert response.status_code == 400 and "SECRET" not in response.text
    assert model.calls == 0


def test_boundary_size_media_origin_and_invalid_id(host):
    with TestClient(api.create_app(), base_url="http://127.0.0.1") as client:
        path = "/api/repair-runs"
        assert client.post(path, json=request()).status_code == 403
        assert (
            client.post(
                path, json=request(), headers={"origin": "https://evil.invalid"}
            ).status_code
            == 403
        )
        assert client.get(path + "/catalog", headers={"host": "evil.invalid"}).status_code == 403
        assert (
            client.post(
                path, content=b"x" * 4097, headers={**ORIGIN, "content-type": "application/json"}
            ).status_code
            == 413
        )
        assert client.post(path, content="{}", headers=ORIGIN).status_code == 415
        assert client.get(path + "/bad").status_code == 400
        assert client.post(path + "/bad/cancel", json={}, headers=ORIGIN).status_code == 400
        assert (
            client.post(
                path + "/" + str(uuid4()) + "/cancel", json={"force": True}, headers=ORIGIN
            ).status_code
            == 400
        )
        assert client.get(path + "/" + str(uuid4())).status_code == 404


@pytest.mark.anyio
async def test_cancel_and_busy_preserve_unknown_usage(host):
    service, model = host
    model.wait = True
    app = api.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://127.0.0.1", headers=ORIGIN
        ) as client,
    ):
        data = request()
        assert (await client.post("/api/repair-runs", json=data)).status_code == 202
        await model.entered.wait()
        assert (await client.post("/api/repair-runs", json=request())).status_code == 429
        assert (await client.get("/api/repair-runs/catalog")).json()["slot"]["status"] == "busy"
        stop = await client.post(f"/api/repair-runs/{data['request_id']}/cancel", json={})
        assert stop.status_code == 202 and stop.json()["cancel_requested"]
        await drained(service)
        saved = (await client.get(f"/api/repair-runs/{data['request_id']}")).json()
        assert saved["task"]["usage"]["reserved_tokens"] > 0 and not saved["active"]
        assert (
            await client.post(f"/api/repair-runs/{data['request_id']}/cancel", json={})
        ).status_code == 200
        assert model.calls == 1


@pytest.mark.anyio
async def test_http_waiter_disconnect_during_preflight_keeps_owner(host, monkeypatch):
    service, model = host
    entered, proceed = asyncio.Event(), asyncio.Event()

    async def wait(root):
        entered.set()
        await proceed.wait()

    monkeypatch.setattr(catalog, "preflight", wait)
    data = RepairRequest(**request())
    waiter = asyncio.create_task(service.submit(data))
    await entered.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert service.tasks
    proceed.set()
    await drained(service)
    assert model.calls == 1
    assert (await service.submit(data)).status == 200
    await service.close()


@pytest.mark.anyio
async def test_shutdown_stops_running_and_rejects_new_work(host):
    service, model = host
    model.wait = True
    data = RepairRequest(**request())
    assert (await service.submit(data)).status == 202
    await model.entered.wait()
    await service.close()
    assert not service.tasks
    assert (await service.submit(RepairRequest(**request()))).status == 503
    result = await service.read(data.request_id)
    assert result.body["cancel_requested"] and result.body["task"]["phase"] == "finished"
    assert model.calls == 1


@pytest.mark.anyio
async def test_catalog_get_does_not_retire_or_release_abandoned_receipt(web):
    w = web.setup()
    # Close real owner locks, as if the process died before consuming its claim.
    w.fence.close()
    w.owner.close()
    service = RepairService(w.store.directory, image_root=w.ctx.image, config_loader=config)
    before = w.store.receipt(w.request.request_id)
    assert (await service.catalog()).body["slot"]["status"] == "recovery_required"
    assert (await service.read(w.request.request_id)).status == 200
    assert w.store.receipt(w.request.request_id) == before


@pytest.mark.anyio
async def test_missing_store_get_never_initializes(tmp_path):
    service = RepairService(tmp_path / "absent", config_loader=config)
    assert (await service.catalog()).status == 503
    assert not service.directory.exists()


@pytest.mark.anyio
async def test_commit_unknown_never_executes_or_reissues_claim(host, monkeypatch):
    service, model = host
    original = WebRepairStore.admit

    def unknown(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise StoreError("store_unavailable")

    monkeypatch.setattr(WebRepairStore, "admit", unknown)
    data = RepairRequest(**request())
    assert (await service.submit(data)).status == 503
    await drained(service)
    assert model.calls == 0
    assert (await service.submit(data)).status == 200
    assert (await service.read(data.request_id)).body["active"]
    assert model.calls == 0
    await service.close()
