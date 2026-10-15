"""P1-01b B4: real API/SQLite/MCP/Docker, explicitly stubbed model decisions.

The cancellation barrier is after the actual SDK tools/call response. It only
pauses control flow; it never replaces Docker, transport or cleanup results.
"""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from agent_workbench.api import create_app
from agent_workbench.mcp_adapter import _Run
from agent_workbench.mcp_config import ROOT, canonical, digest
from agent_workbench.model_gateway.gateway import Config, PreparedCall, Reply
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.docker import DockerControl
from agent_workbench.runner.service import verified_image
from agent_workbench.web_analyses.service import AnalysisService
from agent_workbench.web_analyses.store import WebAnalysisStore

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("AWB_WEB_ANALYSIS_DOCKER") != "1",
        reason="requires AWB_WEB_ANALYSIS_DOCKER=1 and explicitly prepared image",
    ),
]
ORIGIN = {"origin": "http://127.0.0.1:3010"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DeterministicReproductionModel:
    """Test-only model adapter; every T05 operation still executes the real tool."""

    config_sha256 = "a" * 64

    def __init__(self):
        self.roles = []
        self.calls = 0

    def prepare(self, role, messages, output_cap):
        self.roles.append(role)
        raw = canonical(messages)
        return PreparedCall(raw, digest(raw), 1000, 256, "b" * 64)

    async def send(self, prepared, timeout):
        self.calls += 1
        context = json.loads(json.loads(prepared.body)[1]["content"])
        if self.calls == 1:
            tool = next(
                item
                for item in context["available_requests"]
                if item["tool"] == "request_reproduction"
            )
            tool["request_id"] = str(uuid4())
            decision = {"action": "request_tool", "request": tool}
        else:
            diagnosis = self.roles[-1] == "diagnosis"
            decision = {
                "action": "conclude",
                "assessment": "hypothesis" if diagnosis else "proposal_reviewed",
                "reason_code": "contract_mismatch" if diagnosis else "proposal_requires_execution",
                "evidence_refs": context["task"]["evidence"],
            }
        return Reply(decision=canonical(decision), input_tokens=20, output_tokens=10)


@pytest.mark.anyio
@pytest.mark.parametrize("stop", ["none", "http_cancel", "lifespan_shutdown"])
async def test_real_http_analysis_t05_completion_and_cleanup(tmp_path, monkeypatch, stop):
    directory = tmp_path / "state"
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    monkeypatch.delenv("AWB_FRONTEND_PORT", raising=False)
    image_root = Path(os.environ.get("AWB_TEST_IMAGE_ROOT", str(ROOT)))
    manifest = verified_image(image_root)  # Source hash and actual prepared image required.
    store = WebAnalysisStore(directory)
    store.initialize()
    model = DeterministicReproductionModel()
    service = AnalysisService(
        directory,
        image_root=image_root,
        config_loader=lambda: Config(
            "http://never-contacted.invalid",
            "deepseek-flash",
            "synthetic-not-a-real-key",
            "deepseek-v4.1-flash-1m-v1",
        ),
        adapter_factory=lambda _: model,
    )
    invoked = asyncio.Event()
    if stop != "none":
        original_session = _Run.session

        async def pause_after_real_call(self, *args):
            await original_session(self, *args)
            assert self.sent and self.received
            invoked.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(_Run, "session", pause_after_real_call)

    task_id = str(uuid4())
    payload = {"request_id": task_id, "case_name": "output_mismatch", "intent": "diagnose"}
    app = create_app()
    try:
        async with asyncio.timeout(60):
            async with app.router.lifespan_context(app):
                app.state.analysis_runs = service
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
                ) as client:
                    response = await client.post("/api/analysis-runs", json=payload, headers=ORIGIN)
                    assert response.status_code == 202, response.text
                    if stop != "none":
                        await asyncio.wait_for(invoked.wait(), 20)
                        active = store.get(task_id).summary
                        assert active.state.phase != "finished"
                        assert len(active.execution_record_ids) == 1
                        runs = RunStore(directory)
                        try:
                            attempt = runs.detail(active.execution_record_ids[0]).run.attempt_id
                        finally:
                            runs.close()
                        assert attempt is not None
                        control = await DockerControl.connect()
                        running = await control.inspect("awb-p003-" + attempt)
                        assert running is not None and running["State"]["Running"]
                        if stop == "http_cancel":
                            cancelled = await client.post(
                                f"/api/analysis-runs/{task_id}/cancel", json={}, headers=ORIGIN
                            )
                            assert cancelled.status_code == 202
                    if stop != "lifespan_shutdown":
                        while service.tasks:
                            await asyncio.sleep(0.02)
                        replay = await client.post(
                            "/api/analysis-runs", json=payload, headers=ORIGIN
                        )
                        assert replay.status_code == 200 and replay.json()["reused"]
            # The shutdown variant reaches this only after lifespan has waited for cleanup.
        summary = store.get(task_id).summary
        assert summary.state.outcome == ("diagnosis_complete" if stop == "none" else "cancelled")
        assert len(summary.execution_record_ids) == 1
        report = store.read_report(task_id, summary.execution_record_ids[0])
        assert report.execution.cleanup == "removed"
        assert report.execution.image_id == manifest.image_id
        assert report.execution.source_sha256 == manifest.source_sha256
        assert report.execution.scenario == "wrong_type"
        assert report.mcp.source.protocol_version == "2025-11-25"
        # Response was actually observed before either controlled interruption.
        assert report.mcp.adapter_outcome == "completed"
        assert report.mcp.contract_report is not None
        if stop == "none":
            assert report.mcp.contract_report.status == "failed"
            assert any(
                item.code == "output_schema_violation"
                and item.instance_path == "/result/structured_content/count"
                for item in report.mcp.contract_report.findings
            )
        else:
            assert report.mcp.contract_report.status == "inconclusive"
            assert any(item.code == "run_cancelled" for item in report.mcp.contract_report.findings)
            assert store.cancellation_requested(task_id)
        assert model.calls == (3 if stop == "none" else 1)
        assert summary.usage.tool_calls == 1
        assert summary.usage.model_calls == model.calls
        assert not service.tasks
        assert store.active_id() is None
        control = await DockerControl.connect()
        assert await control.inspect("awb-p003-" + report.run_id) is None
        if artifact_directory := os.environ.get("AWB_WEB_ANALYSIS_ARTIFACT_DIR"):
            target = Path(artifact_directory)
            target.mkdir(parents=True, exist_ok=True)
            (target / (stop + ".json")).write_bytes(
                canonical(
                    {
                        "test": "http_analysis_t05_real_docker",
                        "model": "deterministic_stub_no_gateway",
                        "source": "reviewed_synthetic_output_mismatch",
                        "cancellation_boundary": "none"
                        if stop == "none"
                        else "after_real_sdk_response_before_tool_completion",
                        "stop": stop,
                        "summary": summary.model_dump(mode="json"),
                        "report": report.model_dump(mode="json"),
                        "exact_container_absent": True,
                        "active_slot_released": True,
                    }
                )
            )
    finally:
        await service.close()
        store.close()
