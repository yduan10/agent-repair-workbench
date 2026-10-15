"""P1-01b B2: real HTTP/SQLite, fake model transport; no external calls."""

import asyncio
import json
import sqlite3
from uuid import uuid4

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from agent_workbench.analysis_store.fencing import AnalysisFence
from agent_workbench.api import create_app
from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.mcp_models import MCPReport
from agent_workbench.model_gateway.gateway import Config, GatewayError, PreparedCall, Reply
from agent_workbench.models import Finding
from agent_workbench.orchestration.runtime import AnalysisRuntime
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from agent_workbench.web_analyses.fencing import AnalysisWebFence
from agent_workbench.web_analyses.models import WEB_BUDGET, AnalysisRequest
from agent_workbench.web_analyses.service import POLICY_SHA256, AnalysisService
from agent_workbench.web_analyses.store import WebAnalysisStore

ORIGIN = {"origin": "http://127.0.0.1:3010"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def host(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    monkeypatch.delenv("AWB_FRONTEND_PORT", raising=False)
    for key in ("BASE_URL", "NAME", "API_KEY", "LIMIT_PROFILE"):
        monkeypatch.delenv("AWB_MODEL_" + key, raising=False)
    store = WebAnalysisStore(directory)
    store.initialize()
    yield store
    store.close()


def request(intent="diagnose"):
    return AnalysisRequest(request_id=str(uuid4()), case_name="output_mismatch", intent=intent)


def config():
    return Config(
        "http://model.invalid", "deepseek-flash", "test-only", "deepseek-v4.1-flash-1m-v1"
    )


class FakeModel:
    config_sha256 = "a" * 64

    def __init__(self, mode="wait"):
        self.mode = mode
        self.called = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    def prepare(self, role, messages, output_cap):
        raw = canonical(messages)
        return PreparedCall(raw, digest(raw), 1000, 64, "b" * 64)

    async def send(self, prepared, timeout):
        self.calls += 1
        self.called.set()
        if self.mode == "wait":
            await self.release.wait()
        return Reply(
            decision=canonical(
                {
                    "action": "conclude",
                    "assessment": "inconclusive",
                    "reason_code": "evidence_missing",
                    "evidence_refs": [],
                }
            ),
            input_tokens=20,
            output_tokens=10,
        )


def owner(host, model):
    return AnalysisService(host.directory, config_loader=config, adapter_factory=lambda _: model)


async def drained(service):
    async with asyncio.timeout(5):
        while service.tasks:
            await asyncio.sleep(0.01)


@pytest.mark.parametrize(
    "extra",
    [
        {"argv": ["SENSITIVE"]},
        {"model": "other"},
        {"base_url": "http://evil"},
        {"api_key": "SENSITIVE"},
        {"intent": "edit"},
        {"case_name": "../../private"},
        {"request_id": "INVALID"},
    ],
)
def test_strict_body_no_side_effect(host, extra):
    payload = request().model_dump() | extra
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post("/api/analysis-runs", json=payload, headers=ORIGIN)
        assert response.status_code == 400
        assert "SENSITIVE" not in response.text
    assert host.list() == []


@pytest.mark.parametrize(
    "raw,status",
    [
        (b'{"request_id":NaN}', 400),
        (b'{"intent":"diagnose","intent":"check_only"}', 400),
        (b" " * 4097, 413),
        (b"SENSITIVE", 400),
    ],
)
def test_body_limits(host, raw, status):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/analysis-runs", content=raw, headers=ORIGIN | {"content-type": "application/json"}
        )
        assert response.status_code == status
        assert "SENSITIVE" not in response.text
    assert host.list() == []


@pytest.mark.parametrize("headers", [{}, {"origin": "http://evil"}, ORIGIN | {"host": "evil"}])
def test_http_boundary(host, headers):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post("/api/analysis-runs", json=request().model_dump(), headers=headers)
        assert response.status_code in (400, 403)
        assert response.headers["cache-control"] == "no-store"
    assert host.list() == []


def test_real_check_only_and_replay_without_model_config(host):
    payload = request("check_only").model_dump()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        catalog = client.get("/api/analysis-runs/catalog").json()
        assert catalog["model"] == {"configured": False, "reason": "MODEL_NOT_CONFIGURED"}
        assert catalog["slot"] == {"status": "available", "task_id": None}
        rejected = client.post("/api/analysis-runs", json=request().model_dump(), headers=ORIGIN)
        assert rejected.status_code == 503 and host.list() == []
        response = client.post("/api/analysis-runs", json=payload, headers=ORIGIN)
        assert response.status_code == 202 and response.json()["reused"] is False
        assert response.json()["task_id"] == payload["request_id"]
        replay = client.post("/api/analysis-runs", json=payload, headers=ORIGIN)
        assert replay.status_code == 200 and replay.json()["reused"] is True
        assert (
            client.post(
                "/api/analysis-runs", json=payload | {"case_name": "passing"}, headers=ORIGIN
            ).status_code
            == 409
        )
    saved = host.get(payload["request_id"])
    assert saved.summary.state.outcome == "check_complete"
    assert saved.summary.usage.model_calls == 0
    assert len(host.list()) == 1


@pytest.mark.anyio
async def test_two_workers_busy_duplicate_and_cancel(host):
    model = FakeModel()
    first, second = owner(host, model), owner(host, model)
    req = request()
    try:
        response = await first.submit(req)
        assert response.status == 202
        await asyncio.wait_for(model.called.wait(), 3)
        duplicate = await second.submit(req)
        assert duplicate.status == 200 and duplicate.body["reused"]
        assert (await second.submit(request())).status == 429
        assert (await second.catalog()).body["slot"] == {
            "status": "busy",
            "task_id": req.request_id,
        }
        assert (await second.cancel(req.request_id)).status == 202
        assert (await second.cancel(req.request_id)).status in (200, 202)
        await drained(first)
        saved = host.get(req.request_id).summary
        assert saved.state.outcome == "cancelled" and saved.usage.model_calls == 1
        assert saved.usage.usage_complete is False
        assert saved.usage.reserved_tokens == 1064
        assert model.calls == 1
        assert (await second.cancel(req.request_id)).body["status"] == "already_finished"
        assert (await second.catalog()).body["slot"]["status"] == "available"
    finally:
        await first.close()
        await second.close()


@pytest.mark.anyio
async def test_http_disconnect_does_not_cancel_accepted_owner(host, monkeypatch):
    model = FakeModel()
    service = owner(host, model)
    app = create_app()
    req = request()
    async with app.router.lifespan_context(app):
        app.state.analysis_runs = service
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            original = service.submit
            received = asyncio.Event()

            async def lost_response(value):
                result = await original(value)
                received.set()
                await asyncio.Future()
                return result

            monkeypatch.setattr(service, "submit", lost_response)
            pending = asyncio.create_task(
                client.post("/api/analysis-runs", json=req.model_dump(), headers=ORIGIN)
            )
            await asyncio.wait_for(received.wait(), 3)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            await asyncio.wait_for(model.called.wait(), 3)
            assert host.get(req.request_id).summary.state.phase != "finished"
            monkeypatch.setattr(service, "submit", original)
            replay = await client.post("/api/analysis-runs", json=req.model_dump(), headers=ORIGIN)
            assert replay.status_code == 200 and model.calls == 1
            cancelled = await client.post(
                f"/api/analysis-runs/{req.request_id}/cancel", json={}, headers=ORIGIN
            )
            assert cancelled.status_code == 202
    assert host.get(req.request_id).summary.state.outcome == "cancelled"


@pytest.mark.anyio
async def test_shutdown_cancels_and_waits_terminal(host):
    model = FakeModel()
    service = owner(host, model)
    req = request()
    await service.submit(req)
    await asyncio.wait_for(model.called.wait(), 3)
    await asyncio.wait_for(service.close(), 3)
    assert not service.tasks
    assert host.get(req.request_id).summary.state.outcome == "cancelled"
    assert host.cancellation_requested(req.request_id)
    assert (await service.submit(request())).body == {"error": "service_stopping"}


@pytest.mark.anyio
async def test_receipt_replay_precedes_model_config_and_gone(host):
    service = owner(host, FakeModel("finish"))
    req = request()
    await service.submit(req)
    await drained(service)

    def missing():
        raise GatewayError("MODEL_NOT_CONFIGURED")

    service.config_loader = missing
    assert (await service.submit(req)).status == 200
    with sqlite3.connect(host._base.path) as connection:
        connection.execute("DELETE FROM analysis_events WHERE task_id = ?", (req.request_id,))
        connection.execute("DELETE FROM analysis_summaries WHERE task_id = ?", (req.request_id,))
    assert (await service.submit(req)).status == 410
    await service.close()


@pytest.mark.anyio
async def test_orphan_is_recovery_not_resumed(host):
    req = request()
    registry = load_case(
        req.case_name, task_id=req.request_id, intent=req.intent, budget=WEB_BUDGET
    )
    model = FakeModel()
    with AnalysisWebFence(host.directory) as fence:
        with AnalysisFence(host.directory, req.request_id) as task:
            runtime = AnalysisRuntime(registry, host, model)
            host.admit(
                req, runtime.initial_summary(), policy_sha256=POLICY_SHA256, owner=fence, fence=task
            )
    service = owner(host, model)
    assert (await service.catalog()).body["slot"] == {
        "status": "recovery_required",
        "task_id": req.request_id,
    }
    assert (await service.submit(req)).status == 200
    assert (await service.submit(request())).body == {"error": "recovery_required"}
    assert model.calls == 0
    await service.close()


@pytest.mark.anyio
async def test_preflight_fault_static_and_zero_calls(host, monkeypatch):
    model = FakeModel()
    service = owner(host, model)

    def bad_case(*args, **kwargs):
        raise ValueError("SENSITIVE")

    monkeypatch.setattr("agent_workbench.web_analyses.service.load_case", bad_case)
    response = await service.submit(request())
    assert response.status == 503 and "SENSITIVE" not in json.dumps(response.body)
    assert host.list() == [] and model.calls == 0
    await service.close()


@pytest.mark.anyio
async def test_cancel_before_claim_execution_is_zero_calls(host, monkeypatch):
    model = FakeModel()
    service = owner(host, model)
    original = service._execute

    async def cancel_first(req, runtime, admission, fence):
        await service.cancel(req.request_id)
        await original(req, runtime, admission, fence)

    monkeypatch.setattr(service, "_execute", cancel_first)
    req = request()
    assert (await service.submit(req)).status == 202
    await drained(service)
    assert host.get(req.request_id).summary.state.outcome == "cancelled"
    assert model.calls == 0
    await service.close()


@pytest.mark.anyio
async def test_concurrent_same_request_executes_once(host):
    model = FakeModel()
    first, second = owner(host, model), owner(host, model)
    req = request()
    results = await asyncio.gather(first.submit(req), second.submit(req))
    assert sorted(result.status for result in results) in ([200, 202], [202, 429])
    await asyncio.wait_for(model.called.wait(), 3)
    assert (await second.submit(req)).status == 200
    assert model.calls == 1 and len(host.list()) == 1
    await first.close()
    await second.close()


@pytest.mark.anyio
@pytest.mark.parametrize("cleanup", ["removed", "unconfirmed"])
async def test_t05_cancel_waits_cleanup_and_unknown_blocks_release(host, monkeypatch, cleanup):
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class ReproduceModel(FakeModel):
        async def send(self, prepared, timeout):
            self.calls += 1
            context = json.loads(json.loads(prepared.body)[1]["content"])
            tool = next(
                item
                for item in context["available_requests"]
                if item["tool"] == "request_reproduction"
            )
            tool["request_id"] = str(uuid4())
            return Reply(
                decision=canonical({"action": "request_tool", "request": tool}),
                input_tokens=20,
                output_tokens=10,
            )

    async def sandbox(config, case, **kwargs):
        started.set()
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            with anyio.CancelScope(shield=True):
                cleaning.set()
                await release.wait()
            return SandboxReport(
                run_id=kwargs["run_id"],
                mcp=MCPReport(
                    invocation_id=str(uuid4()),
                    adapter_outcome="outcome_unknown",
                    preflight_findings=[Finding(code="run_cancelled", phase="evidence")],
                ),
                execution=ExecutionEvidence(cleanup=cleanup, scenario="wrong_type"),
            )

    monkeypatch.setattr("agent_workbench.controlled_tools.runtime.run_sandbox", sandbox)
    model = ReproduceModel()
    service, observer = owner(host, model), owner(host, model)
    req = request()
    try:
        assert (await service.submit(req)).status == 202
        await asyncio.wait_for(started.wait(), 3)
        assert (await observer.cancel(req.request_id)).status == 202
        await asyncio.wait_for(cleaning.wait(), 3)
        assert host.get(req.request_id).summary.state.phase != "finished"
        assert (await observer.submit(request())).status == 429
        release.set()
        await drained(service)
        summary = host.get(req.request_id).summary
        assert len(summary.execution_record_ids) == 1 and model.calls == 1
        assert (
            host.read_report(req.request_id, summary.execution_record_ids[0]).execution.cleanup
            == cleanup
        )
        slot = (await observer.catalog()).body["slot"]
        assert slot["status"] == ("available" if cleanup == "removed" else "recovery_required")
        if cleanup == "unconfirmed":
            assert (await observer.submit(request())).body == {"error": "recovery_required"}
    finally:
        release.set()
        await service.close()
        await observer.close()


@pytest.mark.parametrize(
    "suffix,payload,status",
    [
        ("invalid/cancel", {}, 400),
        (str(uuid4()) + "/cancel", {"command": "SENSITIVE"}, 400),
        (str(uuid4()) + "/cancel", {}, 404),
    ],
)
def test_cancel_validation(host, suffix, payload, status):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post("/api/analysis-runs/" + suffix, json=payload, headers=ORIGIN)
        assert response.status_code == status
        assert "SENSITIVE" not in response.text


@pytest.mark.anyio
async def test_catalog_does_not_migrate_database(tmp_path):
    service = AnalysisService(tmp_path / "missing")
    response = await service.catalog()
    assert response.status == 503
    assert not (tmp_path / "missing" / "state.sqlite3").exists()


@pytest.mark.anyio
async def test_unexpected_config_error_is_static(host):
    def invalid():
        raise ValueError("PRIVATE URL AND KEY")

    service = AnalysisService(host.directory, config_loader=invalid)
    catalog = await service.catalog()
    assert catalog.body["model"] == {"configured": False, "reason": "MODEL_CONFIGURATION_INVALID"}
    response = await service.submit(request())
    assert response.body == {"error": "MODEL_CONFIGURATION_INVALID"}
    assert host.list() == []
    await service.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "intent,roles,outcome",
    [
        ("diagnose", ["diagnosis", "verification"], "diagnosis_complete"),
        ("propose_repair", ["diagnosis", "repair", "verification"], "proposal_only"),
    ],
)
async def test_http_role_pipeline_real_store_fake_model(host, intent, roles, outcome):
    class RoleModel(FakeModel):
        def __init__(self):
            super().__init__()
            self.roles = []

        def prepare(self, role, messages, output_cap):
            self.roles.append(role)
            return super().prepare(role, messages, output_cap)

        async def send(self, prepared, timeout):
            self.calls += 1
            context = json.loads(json.loads(prepared.body)[1]["content"])
            refs = context["task"]["evidence"]
            if self.roles[-1] == "repair":
                source = context["editable_files"][0]
                decision = {
                    "action": "conclude",
                    "disposition": "proposal_only",
                    "evidence_refs": refs,
                    "edits": [
                        {
                            "path": source["path"],
                            "base_sha256": source["base_sha256"],
                            "replacement": "# proposal only\n",
                        }
                    ],
                }
            else:
                decision = {
                    "action": "conclude",
                    "assessment": "hypothesis"
                    if self.roles[-1] == "diagnosis"
                    else "proposal_reviewed",
                    "reason_code": "contract_mismatch"
                    if self.roles[-1] == "diagnosis"
                    else "proposal_requires_execution",
                    "evidence_refs": refs,
                }
            return Reply(decision=canonical(decision), input_tokens=20, output_tokens=10)

    model = RoleModel()
    service = owner(host, model)
    app = create_app()
    req = request(intent)
    async with app.router.lifespan_context(app):
        app.state.analysis_runs = service
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            result = await client.post("/api/analysis-runs", json=req.model_dump(), headers=ORIGIN)
            assert result.status_code == 202
            await drained(service)
            response = await client.get(f"/api/analyses/{req.request_id}")
            assert response.status_code == 200
            assert response.json()["summary"]["state"]["outcome"] == outcome
            assert model.roles == roles
            assert host.get(req.request_id).summary.usage.model_calls == len(roles)
            assert (await client.get("/api/analysis-runs/catalog")).json()["slot"][
                "status"
            ] == "available"


@pytest.mark.anyio
async def test_shutdown_during_preflight_never_admits(host, monkeypatch):
    import threading

    entered, release = threading.Event(), threading.Event()
    original = load_case

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr("agent_workbench.web_analyses.service.load_case", delayed)
    model = FakeModel()
    service = owner(host, model)
    submit = asyncio.create_task(service.submit(request()))
    assert await asyncio.to_thread(entered.wait, 3)
    closing = asyncio.create_task(service.close())
    await asyncio.sleep(0)
    release.set()
    assert (await submit).body == {"error": "service_stopping"}
    await closing
    assert host.list() == [] and model.calls == 0
