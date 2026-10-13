"""W01/03/05/06/08: HTTP lifecycle tests; fake runner explicitly synthetic."""

import asyncio
import threading
from uuid import uuid4

import anyio
import pytest
from fastapi.testclient import TestClient

from agent_workbench.api import create_app
from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Finding, Report
from agent_workbench.run_store.models import StoreError
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from agent_workbench.web_runs import catalog, service
from agent_workbench.web_runs.models import ReproductionRequest
from agent_workbench.web_runs.store import WebRunStore

ORIGIN = {"origin": "http://127.0.0.1:3010"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def result(attempt, *, cancelled=False, sent=False, cleanup="removed"):
    return SandboxReport(
        run_id=attempt,
        mcp=MCPReport(
            invocation_id="synthetic",
            adapter_outcome=(
                "outcome_unknown"
                if cancelled and sent
                else "transport_error"
                if cancelled
                else "completed"
            ),
            contract_report=None if cancelled else Report(status="passed"),
            preflight_findings=[Finding(code="run_cancelled", phase="transport")]
            if cancelled
            else [],
        ),
        execution=ExecutionEvidence(cleanup=cleanup),
    )


@pytest.fixture
def ready(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    monkeypatch.delenv("AWB_FRONTEND_PORT", raising=False)
    store = WebRunStore(directory)
    store.initialize()
    calls = []

    async def prepared(root=None):
        return None

    async def runner(config, case, *, run_id, image_root):
        calls.append(run_id)
        return result(run_id)

    monkeypatch.setattr(catalog, "prepared", prepared)
    monkeypatch.setattr(service, "run_sandbox", runner)
    yield directory, store, calls
    store.close()


def request(scenario="pass", run_id=None):
    return {"request_id": run_id or str(uuid4()), "scenario": scenario}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"request_id": "bad", "scenario": "pass"},
        {"request_id": str(uuid4()).upper(), "scenario": "pass"},
        {"request_id": str(uuid4()), "scenario": "oom"},
        {"request_id": str(uuid4()), "scenario": "pass", "argv": ["SENSITIVE"]},
        {"request_id": 1, "scenario": "pass"},
        [],
        None,
    ],
)
def test_input_rejected_without_execution(ready, payload):
    _, store, calls = ready
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post("/api/reproductions", json=payload, headers=ORIGIN)
        assert response.status_code in (400, 415)
        assert "SENSITIVE" not in response.text
    assert store.list_runs() == [] and calls == []


@pytest.mark.parametrize(
    "raw,code",
    [
        (b'{"scenario":"pass","scenario":"timeout"}', 400),
        (b'{"request_id":NaN}', 400),
        (b"{}" + b" " * 4096, 413),
        (b'{"SENSITIVE":', 400),
    ],
)
def test_raw_limits_and_duplicate_keys(ready, raw, code):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/reproductions", content=raw, headers=ORIGIN | {"content-type": "application/json"}
        )
        assert response.status_code == code
        assert "SENSITIVE" not in response.text
    assert ready[2] == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"origin": "http://127.0.0.1:3011"},
        {"origin": "https://evil.test"},
        ORIGIN | {"sec-fetch-site": "cross-site"},
    ],
)
def test_write_requires_exact_origin(ready, headers):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.post("/api/reproductions", json=request(), headers=headers).status_code == 403
        assert (
            client.post(
                f"/api/reproductions/{uuid4()}/cancel", json={}, headers=headers
            ).status_code
            == 403
        )
    assert ready[2] == []


@pytest.mark.parametrize("port", ["0", "1023", "65536", "abc", "3013/evil", "１２３４", ""])
def test_invalid_origin_port_fails_closed(monkeypatch, port):
    monkeypatch.setenv("AWB_FRONTEND_PORT", port)
    with pytest.raises(ValueError, match="^invalid_frontend_port$"):
        create_app()


def test_configured_origin_does_not_allow_default_port(ready, monkeypatch):
    monkeypatch.setenv("AWB_FRONTEND_PORT", "3013")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.post("/api/reproductions", json=request(), headers=ORIGIN).status_code == 403
        assert (
            client.post(
                "/api/reproductions", json=request(), headers={"origin": "http://localhost:3013"}
            ).status_code
            == 202
        )


def test_new_replay_conflict_restart_and_read_report(ready):
    _, store, calls = ready
    req = request()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        first = client.post("/api/reproductions", json=req, headers=ORIGIN)
        assert first.status_code == 202 and not first.json()["reused"]
        again = client.post("/api/reproductions", json=req, headers=ORIGIN)
        assert again.status_code == 200 and again.json()["reused"]
        assert (
            client.post(
                "/api/reproductions", json=req | {"scenario": "timeout"}, headers=ORIGIN
            ).status_code
            == 409
        )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.post("/api/reproductions", json=req, headers=ORIGIN).status_code == 200
        detail = client.get("/api/runs/" + req["request_id"])
        assert "token" not in detail.text
        assert client.get(f"/api/runs/{req['request_id']}/report").status_code == 200
        assert (
            client.post(
                f"/api/reproductions/{req['request_id']}/cancel", json={}, headers=ORIGIN
            ).json()["status"]
            == "already_finished"
        )
    assert len(calls) == 1
    assert store.active_id() is None


def test_catalog_missing_store_has_no_disk_or_execution(tmp_path, monkeypatch):
    target = tmp_path / "missing"
    monkeypatch.setenv("AWB_STATE_DIR", str(target))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        data = client.get("/api/reproductions/catalog").json()
        assert data["reason"] == "store_not_initialized" and not data["ready"]
        assert [case["id"] for case in data["cases"]] == [
            "pass",
            "tool_error",
            "timeout",
            "response_lost",
        ]
    assert not target.exists()


def test_post_rechecks_environment_but_duplicate_precedes_preparation(ready, monkeypatch):
    req = request()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.get("/api/reproductions/catalog").json()["ready"]

        async def missing(root=None):
            return "image_not_prepared"

        monkeypatch.setattr(catalog, "prepared", missing)
        assert client.post("/api/reproductions", json=req, headers=ORIGIN).status_code == 503
        assert ready[1].list_runs() == [] and ready[2] == []
        # Synthetic committed admission survives a process crash before dispatch.
        from agent_workbench.web_runs.fencing import OwnerFence

        parsed = ReproductionRequest.model_validate(req)
        with OwnerFence(ready[0]) as fence:
            ready[1].admit(parsed, fence)
        assert client.post("/api/reproductions", json=req, headers=ORIGIN).status_code == 200
    assert ready[2] == []


async def wait_finished(owner):
    with anyio.fail_after(3):
        while owner.tasks:
            await anyio.sleep(0.01)


@pytest.mark.anyio
async def test_disconnect_during_admission_does_not_drop_dispatch(ready, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = WebRunStore.admit

    def delayed(self, *args):
        claim = original(self, *args)
        entered.set()
        assert release.wait(3)
        return claim

    monkeypatch.setattr(WebRunStore, "admit", delayed)
    owner = service.ReproductionService(ready[0])
    parsed = ReproductionRequest.model_validate(request())
    http_waiter = asyncio.create_task(owner.submit(parsed))
    assert await anyio.to_thread.run_sync(entered.wait, 3)
    http_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await http_waiter
    release.set()
    await wait_finished(owner)
    assert len(ready[2]) == 1
    assert ready[1].detail(parsed.request_id).run.status == "succeeded"
    assert (await owner.submit(parsed)).status == 200
    await owner.close()


@pytest.mark.anyio
@pytest.mark.parametrize("sent", [False, True])
async def test_cancel_and_busy_are_persistent(ready, monkeypatch, sent):
    entered = anyio.Event()

    async def runner(config, case, *, run_id, image_root):
        ready[2].append(run_id)
        entered.set()
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            return result(run_id, cancelled=True, sent=sent)

    monkeypatch.setattr(service, "run_sandbox", runner)
    owner = service.ReproductionService(ready[0])
    req = ReproductionRequest.model_validate(request())
    assert (await owner.submit(req)).status == 202
    await entered.wait()
    other = service.ReproductionService(ready[0])
    assert (await other.submit(ReproductionRequest.model_validate(request()))).status == 429
    assert (await other.cancel(req.request_id)).status == 202
    await wait_finished(owner)
    assert ready[1].detail(req.request_id).run.status == (
        "outcome_unknown" if sent else "cancelled"
    )
    assert ready[1].active_id() is None
    assert (await other.cancel(req.request_id)).status == 200
    await owner.close()
    await other.close()


@pytest.mark.anyio
async def test_cancel_before_dispatch_is_observed(ready, monkeypatch):
    original = WebRunStore.admit

    def cancel_first(self, *args):
        claim = original(self, *args)
        self.request_cancel(claim.run.run_id)
        return claim

    async def runner(config, case, *, run_id, image_root):
        try:
            await anyio.lowlevel.checkpoint()
            pytest.fail("cancelled admission reached tool")
        except anyio.get_cancelled_exc_class():
            return result(run_id, cancelled=True)

    monkeypatch.setattr(WebRunStore, "admit", cancel_first)
    monkeypatch.setattr(service, "run_sandbox", runner)
    owner = service.ReproductionService(ready[0])
    req = ReproductionRequest.model_validate(request())
    assert (await owner.submit(req)).status == 202
    await wait_finished(owner)
    assert ready[1].detail(req.request_id).run.status == "cancelled"
    await owner.close()


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["admit", "finish"])
async def test_db_failure_never_replays_or_releases_unsafe_slot(ready, monkeypatch, phase):
    def fail(*args, **kwargs):
        raise StoreError("store_busy")

    monkeypatch.setattr(WebRunStore, phase, fail)
    owner = service.ReproductionService(ready[0])
    req = ReproductionRequest.model_validate(request())
    response = await owner.submit(req)
    await wait_finished(owner)
    assert response.status == (503 if phase == "admit" else 202)
    assert len(ready[2]) == (0 if phase == "admit" else 1)
    if phase == "finish":
        assert ready[1].active_id() == req.request_id
        assert (await owner.submit(req)).status == 200
        assert len(ready[2]) == 1
    await owner.close()


@pytest.mark.anyio
async def test_shutdown_cancels_owned_worker_and_waits_for_save(ready, monkeypatch):
    entered = anyio.Event()
    cleaned = []

    async def runner(config, case, *, run_id, image_root):
        entered.set()
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            with anyio.CancelScope(shield=True):
                await anyio.sleep(0.02)
                cleaned.append(run_id)
            return result(run_id, cancelled=True, sent=True)

    monkeypatch.setattr(service, "run_sandbox", runner)
    owner = service.ReproductionService(ready[0])
    req = ReproductionRequest.model_validate(request())
    assert (await owner.submit(req)).status == 202
    await entered.wait()
    await owner.close()
    assert len(cleaned) == 1 and not owner.tasks
    assert ready[1].detail(req.request_id).run.status == "outcome_unknown"
    assert ready[1].active_id() is None
    assert (await owner.submit(req)).body == {"error": "service_stopping"}


@pytest.mark.anyio
async def test_cleanup_unknown_keeps_slot_even_with_saved_report(ready, monkeypatch):
    async def runner(config, case, *, run_id, image_root):
        return result(run_id, cleanup="unconfirmed")

    monkeypatch.setattr(service, "run_sandbox", runner)
    owner = service.ReproductionService(ready[0])
    req = ReproductionRequest.model_validate(request())
    assert (await owner.submit(req)).status == 202
    await wait_finished(owner)
    assert ready[1].detail(req.request_id).run.status == "outcome_unknown"
    assert ready[1].active_id() == req.request_id
    assert (await owner.submit(ReproductionRequest.model_validate(request()))).status == 429
    await owner.close()


@pytest.mark.anyio
async def test_slow_request_body_has_five_second_bound():
    from agent_workbench.web_runs.api import body

    class App:
        class state:
            local_origins = {"http://127.0.0.1:3010"}

    class SlowRequest:
        app = App()
        headers = ORIGIN | {"content-type": "application/json"}

        async def stream(self):
            yield b"{"
            await anyio.sleep(6)
            yield b"}"

    response = await body(SlowRequest())
    assert response.status_code == 408
    assert response.body == b'{"error":"request_timeout"}'


def test_cancel_unknown_and_invalid_payload_are_rejected(ready):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        endpoint = f"/api/reproductions/{uuid4()}/cancel"
        assert client.post(endpoint, json={}, headers=ORIGIN).status_code == 404
        assert client.post(endpoint, json={"SENSITIVE": 1}, headers=ORIGIN).status_code == 400
        assert (
            client.post("/api/reproductions/not-id/cancel", json={}, headers=ORIGIN).status_code
            == 400
        )


@pytest.mark.anyio
async def test_readonly_preparation_has_only_image_inspection(monkeypatch):
    from types import SimpleNamespace

    commands = []
    manifest = SimpleNamespace(image_id="sha256:" + "a" * 64)
    monkeypatch.setattr(catalog, "verified_image", lambda: manifest)

    class Control:
        async def command(self, *args):
            commands.append(args)
            return (manifest.image_id + "\n").encode()

    async def connect():
        return Control()

    monkeypatch.setattr(catalog.DockerControl, "connect", connect)
    assert await catalog.prepared() is None
    assert commands == [("image", "inspect", manifest.image_id, "--format", "{{.Id}}")]


@pytest.mark.anyio
async def test_preparation_errors_are_fixed_codes(monkeypatch):
    def bad_image():
        raise ValueError("SENSITIVE")

    monkeypatch.setattr(catalog, "verified_image", bad_image)
    assert await catalog.prepared() == "image_not_prepared"
    from types import SimpleNamespace

    monkeypatch.setattr(
        catalog, "verified_image", lambda: SimpleNamespace(image_id="sha256:" + "a" * 64)
    )

    async def bad_docker():
        raise catalog.DockerFailure("SENSITIVE")

    monkeypatch.setattr(catalog.DockerControl, "connect", bad_docker)
    assert await catalog.prepared() == "docker_unavailable"
