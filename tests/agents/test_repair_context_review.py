"""Independent progress-context checks with temporary ledgers, no real model/oracle."""

import json

import pytest

from agent_workbench.repair_contracts.codec import decode_role
from agent_workbench.repair_runtime.context import context
from tests.agents.test_repair_controller import controller, execute, uid
from tests.agents.test_repair_tool_bridge import ctx as ctx


def test_same_target_new_id_preserves_one_completed_fact(ctx):
    requests = []
    sent_ids = []

    def read(value):
        if not requests:
            requests.append(
                next(x for x in value["read_tool_templates"] if x["tool"] == "read_source")
            )
        request = {**requests[0], "request_id": uid()}
        sent_ids.append(request["request_id"])
        return {"action": "request_tool", "request": request}

    runtime, adapter = controller(ctx, [read, read, "needs_evidence"], "single_role")
    result = execute(runtime)
    assert result.cursor.task.usage.tool_calls == 2
    completed = adapter.contexts[-1]["completed_reads"]
    assert len(completed) == 1
    assert completed[0]["request"]["request_id"] == sent_ids[-1]
    assert not any(x["tool"] == "read_source" for x in adapter.contexts[-1]["read_tool_templates"])
    assert not runtime._completed_reads


def test_shared_diagnosis_facts_do_not_expand_repair_permissions(ctx):
    runtime, adapter = controller(
        ctx, ["check_contract", "read_source", "request_reproduction", "needs_evidence"]
    )
    execute(runtime)
    value = adapter.contexts[-1]
    assert value["role"] == "repair"
    assert {x["request"]["tool"] for x in value["completed_reads"]} == {
        "check_contract",
        "read_source",
    }
    assert not {x["tool"] for x in value["read_tool_templates"]} & {
        "check_contract",
        "request_reproduction",
        "read_source",
    }
    forbidden = next(
        x for x in value["completed_reads"] if x["request"]["tool"] == "check_contract"
    )
    with pytest.raises(ValueError):
        decode_role(
            json.dumps({"action": "request_tool", "request": forbidden["request"]}).encode(),
            "repair",
        )
    raw = json.dumps(value)
    for private in ("valid_negative", "valid_zero", "oracle_sha256", "replacement", str(ctx.image)):
        assert private not in raw
    for record in value["completed_reads"]:
        assert record["evidence_refs"]


def test_context_limit_rejects_large_completed_evidence(ctx):
    runtime, _ = controller(ctx, ["needs_evidence"])
    result = execute(runtime)
    with pytest.raises(ValueError, match="context_limit"):
        context(runtime.registry, result.cursor, "single", {}, {"large": {"result": "x" * 48000}})
    value = json.loads(context(runtime.registry, result.cursor, "single", {}, {}))
    assert value["completed_reads"] == []
    assert value["execution_progress"] == {
        "reproduction_observed": False,
        "candidate_available": False,
        "comparison_status": None,
    }


def test_completed_materials_clear_after_model_transport_unknown(ctx):
    from agent_workbench.model_gateway.gateway import Reply

    runtime, adapter = controller(ctx, ["read_source", Reply(error="MODEL_TRANSPORT_ERROR")])
    result = execute(runtime)
    assert adapter.contexts[-1]["completed_reads"]
    assert result.cursor.task.outcome == "outcome_unknown"
    assert runtime._completed_reads == runtime._materials == {}


def test_stale_candidate_same_id_changed_parameters_is_conflict(ctx):
    from tests.agents.test_repair_controller import PATCH

    requests = []

    def stale(value):
        request = dict(value["candidate_application_binding"])
        request.update(
            tool="apply_candidate",
            request_id=uid(),
            expected_file_hash="0" * 64,
            replacement=PATCH,
            evidence_refs=[value["evidence_records"][-1]["ref"]],
        )
        requests.append(request)
        return {"action": "request_tool", "request": request}

    def reused_id(value):
        assert value["last_tool_feedback"]["error_code"] == "STALE_VERSION"
        return {
            "action": "request_tool",
            "request": {
                **requests[0],
                "expected_file_hash": value["candidate_application_binding"]["expected_file_hash"],
            },
        }

    runtime, adapter = controller(ctx, ["request_reproduction", stale, reused_id], "single_role")
    result = execute(runtime)
    assert result.cursor.task.error_code == "TOOL_FAILED"
    assert adapter.calls == 3 and result.cursor.task.usage.tool_calls == 1
    assert result.cursor.task.candidate_count == 0
    assert runtime._request_corrections == 1


@pytest.mark.parametrize("flag", ["admitted", "replayed", "cancelled", "requires_reconcile"])
def test_rejection_cannot_retry_if_admitted_replayed_cancelled_or_unknown(ctx, monkeypatch, flag):
    from agent_workbench.repair_runtime.responses import RepairToolResponse, RepairToolResult
    from agent_workbench.repair_runtime.tools import RepairToolBridge

    original = RepairToolBridge.execute

    async def reject(bridge, role, request, *, cursor):
        if flag == "admitted":
            actual = await original(bridge, role, request, cursor=cursor)
            cursor = actual.cursor
        return RepairToolResult(
            RepairToolResponse(
                request_id=request.request_id,
                tool=request.tool,
                status="rejected",
                error_code="PERMISSION_DENIED",
            ),
            cursor,
            **({flag: True} if flag != "admitted" else {}),
        )

    monkeypatch.setattr(RepairToolBridge, "execute", reject)
    runtime, adapter = controller(ctx, ["read_source", "read_source"], "single_role")
    result = execute(runtime)
    assert adapter.calls == 1 and runtime._request_corrections == 0
    assert result.cursor.task.usage.tool_calls == (1 if flag == "admitted" else 0)
    assert runtime._last_tool_feedback is None and not runtime._completed_reads
    if flag == "requires_reconcile":
        assert result.requires_reconcile
    elif flag == "cancelled":
        assert result.cancelled
    else:
        assert result.cursor.task.error_code == "TOOL_FAILED"


def test_correction_quota_survives_success_and_role_transition(ctx):
    from tests.agents.test_repair_controller import wrong_source

    runtime, adapter = controller(
        ctx,
        [
            wrong_source,
            "read_contract",
            wrong_source,
            "request_reproduction",
            wrong_source,
            "read_source",
        ],
    )
    result = execute(runtime)
    assert result.cursor.task.outcome == "inconclusive"
    assert result.cursor.task.error_code == "TOOL_FAILED"
    assert adapter.calls == 5 and adapter.roles[-1] == "repair"
    assert runtime._request_corrections == 2
    assert result.cursor.task.usage.tool_calls == 2
    assert not runtime._completed_reads and runtime._last_tool_feedback is None
