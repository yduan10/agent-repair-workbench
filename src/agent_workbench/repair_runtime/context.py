"""Ephemeral approved resources for one role; never include private oracle steps."""

import json
from typing import cast
from uuid import UUID, uuid5

from pydantic import JsonValue

from agent_workbench.controlled_tools.contracts import target_key
from agent_workbench.controlled_tools.resources import TaskResourceRegistry
from agent_workbench.mcp_config import canonical
from agent_workbench.repair_contracts.common import RepairRole
from agent_workbench.repair_store.models import Mutation


def candidate_identity(cursor: Mutation) -> str:
    return str(
        uuid5(UUID(cursor.task.task_id), f"p006:candidate:{cursor.task.candidate_count + 1}")
    )


def context(
    registry: TaskResourceRegistry,
    cursor: Mutation,
    role: RepairRole,
    materials: dict[str, dict[str, JsonValue]],
    completed_reads: dict[str, dict[str, JsonValue]] | None = None,
    last_tool_feedback: dict[str, JsonValue] | None = None,
) -> str:
    task = registry.task_spec()
    templates = registry.templates("diagnosis" if role == "single" else role)
    completed = completed_reads or {}
    candidate = materials.get("apply_candidate", {})
    comparison = materials.get("compare_candidate", {})
    rejected = comparison.get("status") == "rejected" and comparison.get(
        "candidate_id"
    ) == candidate.get("candidate_id")
    observed = materials.get("request_reproduction", {}).get("status") == "observed_failure"
    stage = (
        "revise_candidate"
        if rejected
        else "compare_candidate"
        if candidate.get("status") == "committed"
        else "propose_candidate"
        if observed
        else "reproduce_failure"
    )
    may_propose = role in ("single", "repair") and stage in (
        "propose_candidate",
        "revise_candidate",
    )
    value = {
        "task_id": task.task_id,
        "mode": cursor.task.mode,
        "role": role,
        "budget": cursor.task.budget.model_dump(mode="json"),
        "usage": cursor.task.usage.model_dump(mode="json"),
        "baseline_tree_hash": cursor.task.baseline.tree_sha256,
        "baseline_file_hash": cursor.task.baseline.file_sha256,
        "next_candidate_id": candidate_identity(cursor),
        "next_stage": stage,
        "candidate_count": cursor.task.candidate_count,
        "candidate_application_binding": {
            "candidate_id": candidate_identity(cursor),
            "expected_baseline_hash": cursor.task.baseline.tree_sha256,
            "expected_file_hash": cursor.task.baseline.file_sha256,
        }
        if may_propose
        else None,
        "candidate_comparison_binding": {
            "candidate_id": candidate.get("candidate_id"),
            "expected_candidate_tree_hash": candidate.get("candidate_tree_hash"),
        }
        if stage == "compare_candidate" and role in ("single", "verification")
        else None,
        "last_tool_feedback": last_tool_feedback,
        "evidence_records": [
            {
                "ref": ref.model_dump(mode="json"),
                **registry.evidence(ref, "summary"),
                **registry.evidence(ref, "findings"),
            }
            for ref in task.evidence
        ],
        "read_tool_templates": [
            item.model_dump(mode="json")
            for item in templates
            if target_key(item) not in completed
            and (item.tool != "request_reproduction" or "request_reproduction" not in materials)
        ],
        "completed_reads": list(completed.values()),
        "execution_progress": {
            "reproduction_observed": materials.get("request_reproduction", {}).get("status")
            == "observed_failure",
            "candidate_available": "apply_candidate" in materials,
            "comparison_status": comparison.get("status")
            if comparison.get("candidate_id") == candidate.get("candidate_id")
            else None,
        },
        "tool_materials": materials,
    }
    raw = canonical(cast(dict[str, JsonValue], value))
    if len(raw) > 48000:
        raise ValueError("context_limit")
    # No prior role conversation, raw model decisions or replacement enters this context.
    return json.dumps(json.loads(raw), ensure_ascii=True, separators=(",", ":"))
