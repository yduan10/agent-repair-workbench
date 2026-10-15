"""Independent B2 lifecycle boundaries. Temporary SQLite, no model network/Docker."""

import asyncio
import os
import signal
import subprocess
import sys
import threading

import pytest

from agent_workbench.orchestration.runtime import AnalysisRuntime
from tests.test_web_analysis_service import FakeModel, drained, owner, request

pytest_plugins = ("tests.test_web_analysis_service",)


@pytest.mark.anyio
async def test_owner_in_different_process_and_sigstop_cannot_be_reclaimed(host):
    script = (
        "from pathlib import Path; import sys; "
        "from agent_workbench.web_analyses.fencing import AnalysisWebFence; "
        "f=AnalysisWebFence(Path(sys.argv[1])); f.acquire(); "
        "print('ready', flush=True); sys.stdin.readline(); f.close()"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(host.directory)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    service = owner(host, FakeModel("finish"))
    try:
        assert await asyncio.wait_for(asyncio.to_thread(process.stdout.readline), 5) == "ready\n"
        assert (await service.catalog()).status == 429
        os.kill(process.pid, signal.SIGSTOP)
        assert (await service.submit(request("check_only"))).status == 429
        assert host.list() == []
        os.kill(process.pid, signal.SIGCONT)
        process.stdin.write("stop\n")
        process.stdin.flush()
        assert await asyncio.to_thread(process.wait, 5) == 0
        assert (await service.catalog()).body["slot"]["status"] == "available"
        req = request("check_only")
        assert (await service.submit(req)).status == 202
        await drained(service)
        assert host.get(req.request_id).summary.state.outcome == "check_complete"
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGCONT)
            process.terminate()
        await asyncio.to_thread(process.wait, 5)
        process.stdin.close()
        process.stdout.close()
        await service.close()


@pytest.mark.anyio
async def test_submit_waiter_lost_before_admission_keeps_single_owner(host, monkeypatch):
    from agent_workbench.web_analyses import service as module

    entered, release = threading.Event(), threading.Event()
    original = module.load_case

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "load_case", delayed)
    service = owner(host, FakeModel("finish"))
    req = request("check_only")
    waiting = asyncio.create_task(service.submit(req))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        release.set()
        await drained(service)
        assert (await service.submit(req)).status == 200
        await drained(service)
        assert len(host.list()) == 1
        assert host.get(req.request_id).summary.state.outcome == "check_complete"
    finally:
        release.set()
        await service.close()


@pytest.mark.anyio
async def test_cancel_unknown_does_not_cancel_existing_owner(host):
    model = FakeModel()
    service = owner(host, model)
    req = request()
    try:
        assert (await service.submit(req)).status == 202
        await asyncio.wait_for(model.called.wait(), 3)
        unknown = request()
        assert (await service.cancel(unknown.request_id)).status == 404
        assert not host.cancellation_requested(req.request_id)
        assert model.calls == 1
        assert host.get(req.request_id).summary.state.phase != "finished"
    finally:
        await service.close()


@pytest.mark.anyio
async def test_runtime_failure_after_admission_requires_explicit_recovery(host, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_EXCEPTION")

    monkeypatch.setattr(AnalysisRuntime, "run_created", fail)
    service = owner(host, FakeModel())
    req = request()
    assert (await service.submit(req)).status == 202
    await drained(service)
    catalog = await service.catalog()
    assert catalog.body["slot"] == {"status": "recovery_required", "task_id": req.request_id}
    assert "PRIVATE_EXCEPTION" not in str(catalog.body)
    assert (await service.submit(req)).status == 200
    assert (await service.submit(request())).body == {"error": "recovery_required"}
    await service.close()


@pytest.mark.anyio
async def test_cancellation_channel_failure_stops_model_and_keeps_unknown_usage(host, monkeypatch):
    from agent_workbench.web_analyses.store import WebAnalysisStore

    model = FakeModel()
    service = owner(host, model)
    req = request()
    try:
        assert (await service.submit(req)).status == 202
        await asyncio.wait_for(model.called.wait(), 3)

        def failed_read(*args, **kwargs):
            raise RuntimeError("PRIVATE_DB_FAILURE")

        monkeypatch.setattr(WebAnalysisStore, "cancellation_requested", failed_read)
        await drained(service)
        summary = host.get(req.request_id).summary
        assert summary.state.phase == "finished"
        assert summary.usage.usage_complete is False
        assert summary.usage.reserved_tokens > 0
        assert model.calls == 1
    finally:
        await service.close()


@pytest.mark.anyio
async def test_persistent_cancel_after_graph_scheduled_prevents_first_model(host, monkeypatch):
    original = AnalysisRuntime.turn
    model = FakeModel("finish")
    service = owner(host, model)
    req = request()

    async def cancellation_before_first_turn(runtime, role):
        host.request_cancel(req.request_id)
        return await original(runtime, role)

    monkeypatch.setattr(AnalysisRuntime, "turn", cancellation_before_first_turn)
    assert (await service.submit(req)).status == 202
    await drained(service)
    summary = host.get(req.request_id).summary
    assert summary.state.outcome == "cancelled"
    assert model.calls == 0 and summary.usage.model_calls == 0
    assert summary.usage.reserved_tokens == 0
    await service.close()
