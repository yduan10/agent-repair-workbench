"""H3 fixed profile entry gates; model and oracle reports here are synthetic."""

import asyncio
import json
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution import compare as comparison
from agent_workbench.cli import main
from agent_workbench.controlled_tools.resources import load_repair_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_cases.profiles import get_profile
from agent_workbench.repair_runtime import tools as bridge
from agent_workbench.repair_runtime.controller import RepairController
from tests.agents.test_repair_cli import configured as configured
from tests.agents.test_repair_controller import Scripted
from tests.agents.test_repair_tool_bridge import ctx as ctx


@pytest.mark.parametrize("mode", ["single_role", "three_role"])
@pytest.mark.parametrize("case_id", ["output_mismatch", "counter_offset"])
def test_cli_profile_selected_and_exact_current_result(
    ctx, configured, monkeypatch, capsys, mode, case_id
):
    original = ctx.oracle

    async def synthetic_report(snapshot, **kwargs):
        result = await original(snapshot, **kwargs)
        if (
            snapshot.ref.kind == "baseline"
            and snapshot.ref.manifest_sha256 == get_profile("counter_offset").manifest_sha256
        ):
            result = result.model_copy(
                update={
                    "steps": list(
                        s.model_copy(update={"code": "count_value"})
                        if s.code == "count_type"
                        else s
                        for s in result.steps
                    )
                }
            )
        return result

    monkeypatch.setattr(bridge, "run_oracle", synthetic_report)
    monkeypatch.setattr(comparison, "run_oracle", synthetic_report)
    assert main(["repair", "--case", case_id, "--mode", mode]) == 0
    result = json.loads(capsys.readouterr().out)
    task = result["task"]
    assert task["baseline"]["manifest_sha256"] == get_profile(case_id).manifest_sha256
    assert task["outcome"] == "candidate_verified" and task["mode"] == mode
    assert task["usage"]["model_calls"] == 3 and len(ctx.attempts) == 5
    assert task["budget"]["candidates"] == 2
    # New profile's initial evidence is honestly schema-passing, not a fake type finding.
    if case_id == "counter_offset":
        assert configured[0].contexts[0]["evidence_records"][0]["summary"]["status"] == "passed"
    for context in configured[0].contexts:
        assert "failure_code" not in context and "profile_digest" not in context


@pytest.mark.parametrize("case_id", ["passing", "../private", "unknown"])
def test_cli_unknown_case_rejected_before_adapter(ctx, configured, capsys, case_id):
    with pytest.raises(SystemExit) as error:
        main(["repair", "--case", case_id])
    assert error.value.code == 2
    assert configured == [] and ctx.attempts == []
    # argparse validation must continue using the existing sanitised error path.
    assert case_id not in capsys.readouterr().err


@pytest.mark.parametrize("case_id", ["output_mismatch", "counter_offset"])
def test_controller_cross_profile_rejected_before_any_request(ctx, case_id):
    other = "counter_offset" if case_id == "output_mismatch" else "output_mismatch"
    baseline = ctx.snapshots.create_baseline(str(uuid4()), case_id=case_id)
    registry = load_repair_case(
        other, task_id=str(uuid4()), budget=Budget(total_tokens=2000000, output_tokens=8192)
    )
    adapter = Scripted(ctx, [])
    runtime = RepairController(
        store=ctx.store,
        snapshots=ctx.snapshots,
        baseline=baseline,
        registry=registry,
        adapter=adapter,
        mode="three_role",
        image_root=ctx.image,
    )
    with pytest.raises(ResourceError, match="PERMISSION_DENIED"):
        asyncio.run(runtime.run())
    assert adapter.calls == 0 and ctx.attempts == []


def test_registry_name_cannot_override_durable_manifest(ctx):
    baseline = ctx.snapshots.create_baseline(str(uuid4()), case_id="counter_offset")
    registry = load_repair_case(
        "counter_offset",
        task_id=str(uuid4()),
        budget=Budget(total_tokens=2000000, output_tokens=8192),
    )
    registry.manifest_sha256 = get_profile("output_mismatch").manifest_sha256
    adapter = Scripted(ctx, [])
    runtime = RepairController(
        store=ctx.store,
        snapshots=ctx.snapshots,
        baseline=baseline,
        registry=registry,
        adapter=adapter,
        mode="single_role",
        image_root=ctx.image,
    )
    with pytest.raises(ResourceError, match="PERMISSION_DENIED"):
        asyncio.run(runtime.run())
    assert adapter.calls == 0 and ctx.attempts == []
