"""Independent 1.4 stage/identity checks, synthetic reports with real temporary ledger."""

import json

import pytest

from agent_workbench.repair_runtime.context import context
from tests.agents.test_repair_controller import controller, execute
from tests.agents.test_repair_tool_bridge import ctx as ctx


@pytest.mark.parametrize("mode", ["single_role", "three_role"])
def test_previous_rejection_is_not_current_candidate_status(ctx, mode):
    async def reject_only_first():
        ctx.candidate_failure = len(ctx.attempts) <= 5

    ctx.oracle_hook = reject_only_first
    runtime, adapter = controller(
        ctx,
        [
            "request_reproduction",
            "apply_candidate",
            "compare_candidate",
            "apply_candidate",
            "compare_candidate",
        ],
        mode,
    )
    result = execute(runtime)
    assert result.cursor.task.outcome == "candidate_verified"
    first, rejected, second = adapter.contexts[2:5]
    assert rejected["next_stage"] == "revise_candidate"
    assert rejected["execution_progress"]["comparison_status"] == "rejected"
    assert second["next_stage"] == "compare_candidate"
    assert second["candidate_application_binding"] is None
    assert second["execution_progress"]["comparison_status"] is None
    assert (
        second["candidate_comparison_binding"]["candidate_id"]
        != first["candidate_comparison_binding"]["candidate_id"]
    )
    assert second["candidate_comparison_binding"]["candidate_id"] != second["next_candidate_id"]
    assert (
        second["tool_materials"]["compare_candidate"]["candidate_id"]
        == first["candidate_comparison_binding"]["candidate_id"]
    )
    assert second["tool_materials"]["compare_candidate"]["status"] == "rejected"


@pytest.mark.parametrize("role", ["diagnosis", "repair", "verification", "single"])
@pytest.mark.parametrize(
    "stage", ["reproduce_failure", "propose_candidate", "compare_candidate", "revise_candidate"]
)
def test_binding_visibility_is_limited_by_stage_and_role(ctx, role, stage):
    materials = {}
    if stage != "reproduce_failure":
        materials["request_reproduction"] = {"status": "observed_failure"}
    if stage in ("compare_candidate", "revise_candidate"):
        materials["apply_candidate"] = {
            "status": "committed",
            "candidate_id": "b" * 36,
            "candidate_tree_hash": "c" * 64,
        }
    if stage == "revise_candidate":
        materials["compare_candidate"] = {"status": "rejected", "candidate_id": "b" * 36}
    value = json.loads(context(ctx.registry, ctx.cursor, role, materials))
    assert value["next_stage"] == stage
    assert bool(value["candidate_application_binding"]) == (
        role in ("single", "repair") and stage in ("propose_candidate", "revise_candidate")
    )
    assert bool(value["candidate_comparison_binding"]) == (
        role in ("single", "verification") and stage == "compare_candidate"
    )
