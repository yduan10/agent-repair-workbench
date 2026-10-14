"""Independent P0-05b B3 lifecycle/accounting probes; no network/model credentials."""

import asyncio
import json
import time
from uuid import uuid4

import anyio

from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.mcp_models import MCPReport
from agent_workbench.model_gateway.gateway import Reply, canonical
from agent_workbench.models import Finding
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.orchestration.runtime import AnalysisRuntime
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from tests.agents.test_runtime import ScriptedAdapter
from tests.agents.test_runtime import host as host


def registry(intent="diagnose"):
    return load_case(
        "output_mismatch",
        task_id=str(uuid4()),
        intent=intent,
        budget=Budget(total_tokens=2000, output_tokens=32),
    )


class ReproduceAdapter(ScriptedAdapter):
    async def send(self, request, timeout):
        messages = json.loads(request.body)
        if self.role == "diagnosis" and len(messages) == 2:
            self.calls.append((self.role, messages))
            context = json.loads(messages[1]["content"])
            tool = next(
                x for x in context["available_requests"] if x["tool"] == "request_reproduction"
            )
            return Reply(
                decision=canonical({"action": "request_tool", "request": tool}),
                input_tokens=20,
                output_tokens=10,
            )
        return await super().send(request, timeout)


def test_native_cancel_during_http_retains_unknown_reservation(host):
    async def run():
        entered = asyncio.Event()

        class Blocking(ScriptedAdapter):
            async def send(self, request, timeout):
                self.calls.append((self.role, []))
                entered.set()
                await asyncio.Event().wait()

        adapter = Blocking()
        runtime = AnalysisRuntime(registry(), host, adapter)
        task = asyncio.create_task(runtime.run())
        await entered.wait()
        task.cancel()
        result = await task
        assert result.summary.state.outcome == "cancelled"
        assert result.summary.usage.reserved_tokens == 1032
        assert result.summary.usage.usage_complete is False
        assert result.summary.usage.known_input_tokens == 0
        assert len(adapter.calls) == 1
        assert host.get(result.summary.task_id).summary == result.summary

    asyncio.run(run())


def test_t05_atomically_links_and_completion_uses_new_summary(host, monkeypatch):
    resource = registry()
    dispatched = []

    async def sandbox(config, case, **kwargs):
        summary = host.get(resource.task_spec().task_id).summary
        assert summary.usage.tool_calls == 1
        assert len(summary.execution_record_ids) == 1
        dispatched.append(kwargs["run_id"])
        return SandboxReport(
            run_id=kwargs["run_id"],
            mcp=MCPReport(
                invocation_id=str(uuid4()),
                adapter_outcome="completed",
                contract_report=resource.initial_report(),
            ),
            execution=ExecutionEvidence(cleanup="removed", scenario="wrong_type"),
        )

    monkeypatch.setattr("agent_workbench.controlled_tools.runtime.run_sandbox", sandbox)
    adapter = ReproduceAdapter()
    result = asyncio.run(AnalysisRuntime(resource, host, adapter).run())
    assert result.summary.state.outcome == "diagnosis_complete"
    assert len(dispatched) == 1 and result.summary.usage.tool_calls == 1
    assert len(result.summary.execution_record_ids) == 1
    events = [x.event.kind for x in host.events(result.summary.task_id)]
    assert events.count("tool_started") == events.count("tool_completed") == 1
    assert (
        host.read_report(result.summary.task_id, result.summary.execution_record_ids[0]).run_id
        == dispatched[0]
    )


def test_native_cancel_t05_waits_cleanup_then_finishes_no_more_models(host, monkeypatch):
    async def run():
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def sandbox(config, case, **kwargs):
            started.set()
            try:
                await anyio.sleep_forever()
            except anyio.get_cancelled_exc_class():
                with anyio.CancelScope(shield=True):
                    await anyio.sleep(0.1)
                    cleaned.set()
                return SandboxReport(
                    run_id=kwargs["run_id"],
                    mcp=MCPReport(
                        invocation_id=str(uuid4()),
                        adapter_outcome="outcome_unknown",
                        preflight_findings=[Finding(code="run_cancelled", phase="evidence")],
                    ),
                    execution=ExecutionEvidence(cleanup="removed", scenario="wrong_type"),
                )

        monkeypatch.setattr("agent_workbench.controlled_tools.runtime.run_sandbox", sandbox)
        adapter = ReproduceAdapter()
        runtime = AnalysisRuntime(registry(), host, adapter)
        task = asyncio.create_task(runtime.run())
        await started.wait()
        task.cancel()
        await asyncio.sleep(0.02)
        task.cancel()
        result = await task
        assert cleaned.is_set(), "analysis_finalized_before_tool_cleanup"
        assert result.summary.state.outcome == "cancelled"
        assert len(adapter.calls) == 1
        assert len(result.summary.execution_record_ids) == 1
        report = host.read_report(result.summary.task_id, result.summary.execution_record_ids[0])
        assert report.execution.cleanup == "removed"
        assert host.get(result.summary.task_id).summary == result.summary

    asyncio.run(run())


def test_needs_evidence_loop_respects_two_proposal_limit(host):
    class Needs(ScriptedAdapter):
        async def send(self, request, timeout):
            if self.role == "verification":
                self.calls.append((self.role, json.loads(request.body)))
                return Reply(
                    decision=canonical(
                        {
                            "action": "conclude",
                            "assessment": "needs_evidence",
                            "reason_code": "evidence_missing",
                            "evidence_refs": [],
                        }
                    ),
                    input_tokens=20,
                    output_tokens=10,
                )
            return await super().send(request, timeout)

    adapter = Needs()
    result = asyncio.run(AnalysisRuntime(registry("propose_repair"), host, adapter).run())
    assert result.summary.state.outcome == "budget_exceeded"
    assert result.summary.proposal_count == 2
    assert sum(role == "repair" for role, _ in adapter.calls) == 2
    assert sum(role == "verification" for role, _ in adapter.calls) == 2


def test_explicit_tracing_disable_overrides_environment(host, monkeypatch):
    import langsmith
    from langsmith.utils import tracing_is_enabled

    traced = []
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(langsmith.Client, "create_run", lambda *a, **k: traced.append(k))

    class Observe(ScriptedAdapter):
        async def send(self, request, timeout):
            assert not tracing_is_enabled()
            return await super().send(request, timeout)

    result = asyncio.run(AnalysisRuntime(registry(), host, Observe()).run())
    assert result.summary.state.outcome == "diagnosis_complete"
    assert traced == []


def test_elapsed_deadline_prevents_next_model_send(host):
    adapter = ScriptedAdapter()
    runtime = AnalysisRuntime(registry(), host, adapter)
    runtime.deadline = time.monotonic() + 14
    result = asyncio.run(runtime.run())
    assert result.summary.state.outcome == "budget_exceeded"
    assert adapter.calls == [] and result.summary.usage.model_calls == 0
