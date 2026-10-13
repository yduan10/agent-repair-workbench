import json

import pytest

from agent_workbench.controlled_tools.contracts import (
    CheckContract,
    ReadEvidence,
    ToolDecision,
    target_key,
)
from agent_workbench.orchestration.codec import decode_role
from agent_workbench.orchestration.contracts import Budget, EvidenceRef, TaskSpec, TaskState
from agent_workbench.orchestration.policy import (
    AuthorizationContext,
    EditableFile,
    PolicyError,
    authorize,
    transition,
)

ID = "00000000-0000-0000-0000-000000000001"
REF = EvidenceRef(evidence_id=ID, sha256="a" * 64)


def task(intent="propose_repair"):
    return TaskSpec(
        task_id=ID,
        intent=intent,
        source_kind="synthetic",
        budget=Budget(total_tokens=1000, output_tokens=100),
        evidence=(REF,),
    )


def test_resource_and_role_grants_are_both_required():
    request = CheckContract(
        request_id=ID, tool="check_contract", case_id=ID, contract_revision="b" * 64
    )
    output = ToolDecision(action="request_tool", request=request)
    grants = AuthorizationContext(
        task_id=ID, evidence_refs=(REF,), allowed_targets=(target_key(request),)
    )
    authorize(task(), "diagnosis", output, grants)
    with pytest.raises(PolicyError, match="PERMISSION_DENIED"):
        authorize(task(), "repair", output, grants)
    with pytest.raises(PolicyError, match="PERMISSION_DENIED"):
        authorize(
            task(), "diagnosis", output, AuthorizationContext(task_id=ID, evidence_refs=(REF,))
        )
    with pytest.raises(PolicyError, match="TASK_SCOPE_MISMATCH"):
        authorize(task(), "diagnosis", output, grants.model_copy(update={"task_id": ID[:-1] + "2"}))


def test_read_evidence_target_grant_cannot_override_task_evidence():
    other = EvidenceRef(evidence_id=ID, sha256="b" * 64)
    request = ReadEvidence(
        request_id=ID, tool="read_evidence", evidence_ref=other, section="findings"
    )
    grants = AuthorizationContext(
        task_id=ID, evidence_refs=(REF,), allowed_targets=(target_key(request),)
    )
    with pytest.raises(PolicyError, match="EVIDENCE_NOT_AUTHORIZED"):
        authorize(task(), "diagnosis", ToolDecision(action="request_tool", request=request), grants)


def test_conclusion_references_and_edit_snapshot_need_host_permission():
    output = decode_role(
        json.dumps(
            {
                "action": "conclude",
                "disposition": "proposal_only",
                "evidence_refs": [REF.model_dump()],
                "edits": [{"path": "tool.py", "base_sha256": "b" * 64, "replacement": "x"}],
            }
        ).encode(),
        "repair",
    )
    grants = AuthorizationContext(
        task_id=ID,
        evidence_refs=(REF,),
        editable_files=(EditableFile(path="tool.py", base_sha256="b" * 64),),
    )
    authorize(task(), "repair", output, grants)
    with pytest.raises(PolicyError, match="EDIT_NOT_AUTHORIZED"):
        authorize(task(), "repair", output, AuthorizationContext(task_id=ID, evidence_refs=(REF,)))
    with pytest.raises(PolicyError, match="EVIDENCE_NOT_AUTHORIZED"):
        authorize(task(), "repair", output, AuthorizationContext(task_id=ID, evidence_refs=()))
    with pytest.raises(PolicyError, match="ROLE_OUTPUT_MISMATCH"):
        authorize(task(), "diagnosis", output, grants)


def test_task_intent_cannot_short_circuit_repair_as_check_complete():
    state = TaskState(task_id=ID, intent="propose_repair")
    state = transition(state, "checking", expected_revision=0)
    with pytest.raises(PolicyError):
        transition(state, "finished", expected_revision=1, outcome="check_complete")
    state = transition(state, "diagnosing", expected_revision=1)
    state = transition(state, "proposing", expected_revision=2)
    state = transition(state, "reviewing", expected_revision=3)
    state = transition(state, "finished", expected_revision=4, outcome="proposal_only")
    assert state.revision == 5
    with pytest.raises(PolicyError):
        transition(state, "checking", expected_revision=5)


def test_check_only_and_stale_transition():
    state = transition(TaskState(task_id=ID, intent="check_only"), "checking", expected_revision=0)
    with pytest.raises(PolicyError):
        transition(state, "diagnosing", expected_revision=1)
    with pytest.raises(PolicyError, match="STALE_VERSION"):
        transition(state, "finished", expected_revision=0, outcome="check_complete")
    assert (
        transition(state, "finished", expected_revision=1, outcome="check_complete").outcome
        == "check_complete"
    )


@pytest.mark.parametrize("intent", ["check_only", "diagnose", "propose_repair"])
def test_initial_cancel_and_premature_success(intent):
    state = TaskState(task_id=ID, intent=intent)
    assert (
        transition(state, "finished", expected_revision=0, outcome="cancelled").outcome
        == "cancelled"
    )
    with pytest.raises(PolicyError, match="PREMATURE_COMPLETION"):
        transition(state, "finished", expected_revision=0, outcome="proposal_only")
