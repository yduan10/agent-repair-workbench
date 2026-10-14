"""Explicit actual T05 SDK/Docker gate; never counted as passing when skipped."""

import os
from pathlib import Path

import anyio
import pytest

from agent_workbench.controlled_tools.runtime import ToolRuntime
from agent_workbench.mcp_config import ROOT, canonical, digest
from agent_workbench.runner.docker import DockerControl
from tests.test_controlled_runtime import execution as execution
from tests.test_controlled_runtime import resources as resources


@pytest.mark.docker
@pytest.mark.skipif(os.environ.get("AWB_TOOL_DOCKER") != "1", reason="requires AWB_TOOL_DOCKER=1")
@pytest.mark.parametrize("resources", ["output_mismatch", "passing"], indirect=True)
def test_actual_t05_source_matched_sdk_docker_reproduction(resources, execution):
    store, request, context = execution

    async def run():
        runtime = ToolRuntime(resources, store=store, image_root=ROOT)
        result = await runtime.execute(
            "diagnosis", request, timeout_seconds=10, reservation=context
        )
        assert result.response.status == "ok", result.response.model_dump_json()
        expected = "failed" if resources.case_name == "output_mismatch" else "passed"
        assert result.response.payload["contract_status"] == expected
        assert result.response.payload["cleanup"] == "removed"
        saved = store.read_report(
            resources.task_spec().task_id, result.response.payload["execution_record_id"]
        )
        assert saved.execution.scenario == ("wrong_type" if expected == "failed" else "pass")
        assert saved.mcp.source.protocol_version == "2025-11-25"
        assert (
            digest(canonical(saved.model_dump(mode="json")))
            == result.response.payload["report_sha256"]
        )
        if expected == "failed":
            assert any(
                item["code"] == "output_schema_violation"
                and item["instance_path"] == "/result/structured_content/count"
                for item in result.response.payload["findings"]
            )
        if output := os.environ.get("AWB_TOOL_ARTIFACT_DIR"):
            directory = Path(output)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / (resources.case_name + ".json")).write_bytes(
                canonical(
                    {
                        "source_kind": "synthetic",
                        "test": "actual_t05_sdk_docker",
                        "tool_response": result.response.model_dump(mode="json"),
                        "report": saved.model_dump(mode="json"),
                    }
                )
            )
        control = await DockerControl.connect()
        assert await control.inspect("awb-p003-" + saved.run_id) is None
        replay = await runtime.execute(
            "diagnosis", request, timeout_seconds=10, reservation=context
        )
        assert replay.response.payload == result.response.payload
        assert replay.summary.usage.tool_calls == 1

    anyio.run(run)


@pytest.mark.docker
@pytest.mark.skipif(os.environ.get("AWB_TOOL_DOCKER") != "1", reason="requires AWB_TOOL_DOCKER=1")
def test_native_repeated_cancel_t05_waits_for_actual_container_cleanup(
    resources, execution, monkeypatch
):
    import asyncio

    from agent_workbench.mcp_adapter import _Run

    store, request, context = execution

    async def run():
        invoked = asyncio.Event()
        cleaning = asyncio.Event()
        original_session = _Run.session
        original_cleanup = DockerControl.cleanup

        async def session(self, *args):
            await original_session(self, *args)  # actual SDK invocation/result, then test pause
            invoked.set()
            await asyncio.Event().wait()

        async def cleanup(self, *args):
            cleaning.set()
            await asyncio.sleep(0.08)  # exercise repeated native cancellation during real cleanup
            return await original_cleanup(self, *args)

        monkeypatch.setattr(_Run, "session", session)
        monkeypatch.setattr(DockerControl, "cleanup", cleanup)
        runtime = ToolRuntime(resources, store=store, image_root=ROOT)
        task = asyncio.create_task(
            runtime.execute("diagnosis", request, timeout_seconds=10, reservation=context)
        )
        await asyncio.wait_for(invoked.wait(), 10)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 5)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        result = await task
        assert result.cancelled is True
        assert result.summary.usage.tool_calls == 1
        record_id = result.response.payload["execution_record_id"]
        saved = store.read_report(resources.task_spec().task_id, record_id)
        assert saved.execution.cleanup == "removed"
        assert result.response.status == "outcome_unknown"  # sent before cancellation
        control = await DockerControl.connect()
        assert await control.inspect("awb-p003-" + saved.run_id) is None
        replay = await runtime.execute(
            "diagnosis", request, timeout_seconds=10, reservation=context
        )
        assert replay.response.payload == result.response.payload
        assert replay.cancelled is False

    asyncio.run(run())
