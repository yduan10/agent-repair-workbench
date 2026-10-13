"""Independent second-batch lifecycle probes; fixed synthetic local data only."""

import asyncio
import json
import os
import sys
import threading
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest
from fastapi.testclient import TestClient

from agent_workbench.api import create_app
from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Finding, Report
from agent_workbench.runner import service as actual_runner
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from agent_workbench.web_runs import catalog, service
from agent_workbench.web_runs.models import ReproductionRequest
from agent_workbench.web_runs.store import WebRunStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    store = WebRunStore(directory)
    store.initialize()
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    monkeypatch.delenv("AWB_FRONTEND_PORT", raising=False)

    async def prepared(root=None):
        return None

    monkeypatch.setattr(catalog, "prepared", prepared)
    yield directory, store
    store.close()


def cancelled(attempt):
    return SandboxReport(
        run_id=attempt,
        mcp=MCPReport(
            invocation_id=str(uuid4()),
            adapter_outcome="outcome_unknown",
            preflight_findings=[Finding(code="run_cancelled", phase="transport")],
        ),
        execution=ExecutionEvidence(cleanup="removed"),
    )


async def finished(owner):
    with anyio.fail_after(4):
        while owner.tasks:
            await anyio.sleep(0.01)


@pytest.mark.anyio
async def test_precancel_real_runner_records_terminal_without_docker_create(isolated, monkeypatch):
    original = WebRunStore.admit
    invoked = []

    def admit_then_cancel(self, *args):
        claim = original(self, *args)
        self.request_cancel(claim.run.run_id)
        return claim

    async def connect():
        await anyio.lowlevel.checkpoint()
        invoked.append("connect_after_checkpoint")
        raise AssertionError("pre-cancel must not issue Docker command")

    monkeypatch.setattr(WebRunStore, "admit", admit_then_cancel)
    monkeypatch.setattr(
        actual_runner,
        "verified_image",
        lambda: SimpleNamespace(image_id="sha256:" + "a" * 64, source_sha256="b" * 64),
    )
    monkeypatch.setattr(actual_runner.DockerControl, "connect", connect)
    owner = service.ReproductionService(isolated[0])
    request = ReproductionRequest(request_id=str(uuid4()), scenario="pass")
    try:
        assert (await owner.submit(request)).status == 202
        await finished(owner)
        detail = isolated[1].detail(request.request_id)
        assert detail.run.status == "cancelled"
        assert isolated[1].report(request.request_id).execution.cleanup == "not_created"
        assert isolated[1].active_id() is None
        assert invoked == []
    finally:
        await owner.close()


@pytest.mark.anyio
async def test_shutdown_before_scope_registration_waits_real_runner_terminal(isolated, monkeypatch):
    original = WebRunStore.admit
    committed, release = threading.Event(), threading.Event()

    def delayed(self, *args):
        claim = original(self, *args)
        committed.set()
        assert release.wait(4)
        return claim

    async def connect():
        await anyio.lowlevel.checkpoint()
        raise AssertionError("shutdown pre-dispatch must not reach Docker")

    monkeypatch.setattr(WebRunStore, "admit", delayed)
    monkeypatch.setattr(
        actual_runner,
        "verified_image",
        lambda: SimpleNamespace(image_id="sha256:" + "a" * 64, source_sha256="b" * 64),
    )
    monkeypatch.setattr(actual_runner.DockerControl, "connect", connect)
    owner = service.ReproductionService(isolated[0])
    request = ReproductionRequest(request_id=str(uuid4()), scenario="pass")
    waiter = asyncio.create_task(owner.submit(request))
    assert await anyio.to_thread.run_sync(committed.wait, 4)
    closing = asyncio.create_task(owner.close())
    await anyio.sleep(0)
    assert owner.stopping and not closing.done()
    release.set()
    assert (await waiter).status == 202
    with anyio.fail_after(4):
        await closing
    assert isolated[1].detail(request.request_id).run.status == "cancelled"
    assert isolated[1].active_id() is None


@pytest.mark.anyio
async def test_other_process_http_cancel_reaches_owner_and_never_dispatches_again(
    isolated, monkeypatch
):
    entered = anyio.Event()
    calls = []

    async def runner(config, case, *, run_id, image_root):
        calls.append(run_id)
        entered.set()
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            return cancelled(run_id)

    monkeypatch.setattr(service, "run_sandbox", runner)
    owner = service.ReproductionService(isolated[0])
    request = ReproductionRequest(request_id=str(uuid4()), scenario="timeout")
    try:
        assert (await owner.submit(request)).status == 202
        await entered.wait()
        code = """
import json,sys
from fastapi.testclient import TestClient
from agent_workbench.api import create_app
with TestClient(create_app(),base_url='http://127.0.0.1') as c:
 r=c.post('/api/reproductions/'+sys.argv[1]+'/cancel',json={},headers={'origin':'http://127.0.0.1:3010'})
 print(json.dumps({'status':r.status_code,'body':r.json()}))
"""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            request.request_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(os.environ),
        )
        with anyio.fail_after(8):
            stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr.decode()
        assert json.loads(stdout) == {
            "status": 202,
            "body": {"run_id": request.request_id, "status": "cancel_requested"},
        }
        await finished(owner)
        assert isolated[1].detail(request.request_id).run.status == "outcome_unknown"
        assert isolated[1].active_id() is None
        assert (await owner.submit(request)).status == 200
        assert len(calls) == 1
    finally:
        await owner.close()


def test_private_claim_and_exception_never_cross_http(isolated, monkeypatch, caplog):
    original = WebRunStore.admit
    tokens = []

    def capture(self, *args):
        claim = original(self, *args)
        tokens.append(claim.token)
        return claim

    async def runner(config, case, *, run_id, image_root):
        raise RuntimeError("PRIVATE_EXCEPTION_" + tokens[0])

    monkeypatch.setattr(WebRunStore, "admit", capture)
    monkeypatch.setattr(service, "run_sandbox", runner)
    request = {"request_id": str(uuid4()), "scenario": "pass"}
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        accepted = client.post(
            "/api/reproductions", json=request, headers={"origin": "http://127.0.0.1:3010"}
        )
        assert accepted.status_code == 202
        detail = client.get("/api/runs/" + request["request_id"])
        replay = client.post(
            "/api/reproductions", json=request, headers={"origin": "http://127.0.0.1:3010"}
        )
        assert replay.status_code == 200
        texts = accepted.text + detail.text + replay.text + caplog.text
        assert tokens[0] not in texts and "PRIVATE_EXCEPTION" not in texts
    assert isolated[1].active_id() == request["request_id"]
    assert isolated[1].detail(request["request_id"]).run.status == "running"


@pytest.mark.anyio
async def test_close_during_preparation_rejects_before_claim(isolated, monkeypatch):
    entered, release = anyio.Event(), anyio.Event()
    calls = []

    async def probe(root=None):
        entered.set()
        await release.wait()
        return None

    async def runner(*args, **kwargs):
        calls.append(1)
        raise AssertionError("shutdown cannot dispatch a new call")

    monkeypatch.setattr(catalog, "prepared", probe)
    monkeypatch.setattr(service, "run_sandbox", runner)
    owner = service.ReproductionService(isolated[0])
    request = ReproductionRequest(request_id=str(uuid4()), scenario="pass")
    waiter = asyncio.create_task(owner.submit(request))
    await entered.wait()
    closing = asyncio.create_task(owner.close())
    await anyio.sleep(0)
    release.set()
    assert (await waiter).body == {"error": "service_stopping"}
    await closing
    assert isolated[1].list_runs() == [] and calls == []


@pytest.mark.anyio
async def test_asgi_request_cancellation_keeps_registered_admission_worker(isolated, monkeypatch):
    import httpx

    original = WebRunStore.admit
    committed, release = threading.Event(), threading.Event()
    calls = []

    def delayed(self, *args):
        claim = original(self, *args)
        committed.set()
        assert release.wait(4)
        return claim

    async def runner(config, case, *, run_id, image_root):
        calls.append(run_id)
        return SandboxReport(
            run_id=run_id,
            mcp=MCPReport(
                invocation_id=str(uuid4()),
                adapter_outcome="completed",
                contract_report=Report(status="passed"),
            ),
            execution=ExecutionEvidence(cleanup="removed"),
        )

    monkeypatch.setattr(WebRunStore, "admit", delayed)
    monkeypatch.setattr(service, "run_sandbox", runner)
    app = create_app()
    request = {"request_id": str(uuid4()), "scenario": "pass"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            http = asyncio.create_task(
                client.post(
                    "/api/reproductions", json=request, headers={"origin": "http://127.0.0.1:3010"}
                )
            )
            assert await anyio.to_thread.run_sync(committed.wait, 4)
            http.cancel()
            with pytest.raises(asyncio.CancelledError):
                await http
            release.set()
            await finished(app.state.reproductions)
            replay = await client.post(
                "/api/reproductions", json=request, headers={"origin": "http://127.0.0.1:3010"}
            )
            assert replay.status_code == 200 and replay.json()["reused"] is True
    assert len(calls) == 1
    assert isolated[1].detail(request["request_id"]).run.status == "succeeded"
    assert isolated[1].active_id() is None
