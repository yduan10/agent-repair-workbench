"""Same-state three-slot composition with instrumented deterministic external boundaries."""

import asyncio
import json
from uuid import uuid4

import pytest

from agent_workbench.mcp_config import canonical
from agent_workbench.mcp_models import MCPReport
from agent_workbench.model_gateway.gateway import Reply
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from agent_workbench.web_analyses.models import AnalysisRequest
from agent_workbench.web_analyses.service import AnalysisService
from agent_workbench.web_analyses.store import WebAnalysisStore
from agent_workbench.web_repairs import service as repair_service
from agent_workbench.web_repairs.models import RepairRequest
from agent_workbench.web_repairs.recovery import WebRepairRecovery
from agent_workbench.web_repairs.service import RepairService
from agent_workbench.web_repairs.store import WebRepairStore
from agent_workbench.web_runs.models import ReproductionRequest
from agent_workbench.web_runs.service import ReproductionService
from agent_workbench.web_runs.store import WebRunStore
from tests.agents.test_repair_controller import Scripted
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_repair_recovery import FakeDocker
from tests.test_web_analysis_service import FakeModel, config
from tests.test_web_repair_api import anyio_backend as anyio_backend


@pytest.mark.anyio
async def test_three_slots_bound_models_and_unknown_resources(ctx, monkeypatch):
    models, resources = set(), set()
    model_peak, resource_peak = [], []
    release_models, release_resources = asyncio.Event(), asyncio.Event()

    async def model_boundary(kind):
        models.add(kind)
        model_peak.append(len(models))
        try:
            await release_models.wait()
        finally:
            models.remove(kind)

    async def resource_boundary(kind):
        assert kind not in resources
        resources.add(kind)
        resource_peak.append(len(resources))
        await release_resources.wait()
        # Unknown resource remains potentially live; retain in the accounting set.

    class AnalysisModel(FakeModel):
        async def send(self, prepared, timeout):
            await model_boundary("analysis")
            self.calls += 1
            context = json.loads(json.loads(prepared.body)[1]["content"])
            tool = next(
                x for x in context["available_requests"] if x["tool"] == "request_reproduction"
            )
            tool["request_id"] = str(uuid4())
            return Reply(
                decision=canonical({"action": "request_tool", "request": tool}),
                input_tokens=20,
                output_tokens=10,
            )

    class RepairModel(Scripted):
        async def send(self, prepared, timeout):
            await model_boundary("repair")
            return await super().send(prepared, timeout)

    async def sandbox(kind, *args, **kwargs):
        await resource_boundary(kind)
        return SandboxReport(
            run_id=kwargs["run_id"],
            mcp=MCPReport(invocation_id="synthetic", adapter_outcome="outcome_unknown"),
            execution=ExecutionEvidence(cleanup="unconfirmed", error="create_unconfirmed"),
        )

    async def reproduction(*args, **kwargs):
        return await sandbox("reproduction", *args, **kwargs)

    async def analysis(*args, **kwargs):
        return await sandbox("analysis", *args, **kwargs)

    async def oracle(*args, **kwargs):
        await resource_boundary("repair")
        report = await ctx.oracle(*args, **kwargs)
        report.status, report.error, report.cleanup = (
            "outcome_unknown",
            "cleanup_unconfirmed",
            "unconfirmed",
        )
        return report

    async def ready(*args):
        return None

    monkeypatch.setattr("agent_workbench.web_runs.catalog.prepared", ready)
    monkeypatch.setattr("agent_workbench.web_repairs.catalog.preflight", ready)
    monkeypatch.setattr("agent_workbench.web_runs.service.run_sandbox", reproduction)
    monkeypatch.setattr("agent_workbench.controlled_tools.runtime.run_sandbox", analysis)
    monkeypatch.setattr("agent_workbench.repair_runtime.tools.run_oracle", oracle)
    monkeypatch.setattr(
        repair_service,
        "WebRepairRecovery",
        lambda store, root: WebRepairRecovery(store, root, FakeDocker()),
    )
    a_model, r_model = AnalysisModel(), RepairModel(ctx, ["request_reproduction"])
    a = AnalysisService(
        ctx.store.directory, config_loader=config, adapter_factory=lambda _: a_model
    )
    r = RepairService(
        ctx.store.directory,
        image_root=ctx.image,
        config_loader=config,
        adapter_factory=lambda _: r_model,
    )
    p = ReproductionService(ctx.store.directory)
    ar = AnalysisRequest(request_id=str(uuid4()), case_name="output_mismatch", intent="diagnose")
    rr = RepairRequest(request_id=str(uuid4()), case_id="output_mismatch", mode="three_role")
    pr = ReproductionRequest(request_id=str(uuid4()), scenario="pass")

    async def until(predicate):
        async with asyncio.timeout(8):
            while not predicate():
                await asyncio.sleep(0.01)

    try:
        accepted = await asyncio.gather(a.submit(ar), r.submit(rr), p.submit(pr))
        assert [v.status for v in accepted] == [202, 202, 202]
        await until(lambda: len(models) == 2 and len(resources) == 1)
        release_models.set()
        await until(lambda: len(resources) == 3)
        assert max(model_peak) == 2 and max(resource_peak) == 3
        assert (await a.submit(ar)).status == 200 and (await r.submit(rr)).status == 200
        assert (await p.submit(pr)).status == 200
        release_resources.set()
        await until(lambda: not (a.tasks or r.tasks or p.tasks))
        for cls, expected in [
            (WebAnalysisStore, ar.request_id),
            (WebRepairStore, rr.request_id),
            (WebRunStore, pr.request_id),
        ]:
            store = cls(ctx.store.directory)
            try:
                assert store.active_id() == expected
            finally:
                store.close()
        assert (await a.submit(ar.model_copy(update={"request_id": str(uuid4())}))).status == 409
        assert (await r.submit(rr.model_copy(update={"request_id": str(uuid4())}))).status == 409
        assert (await p.submit(pr.model_copy(update={"request_id": str(uuid4())}))).status == 429
        assert a_model.calls == r_model.calls == 1 and len(resources) == 3
    finally:
        release_models.set()
        release_resources.set()
        await asyncio.gather(a.close(), r.close(), p.close())
