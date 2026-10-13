"""Pure host policy. Grants come from the host, never from model messages."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from agent_workbench.agents.diagnosis.contracts import DiagnosisConclusion
from agent_workbench.agents.repair.contracts import RepairConclusion
from agent_workbench.agents.verification.contracts import VerificationConclusion
from agent_workbench.controlled_tools.contracts import (
    ReadEvidence,
    RelativePath,
    ToolDecision,
    target_key,
)
from agent_workbench.orchestration.contracts import (
    Contract,
    Digest,
    Identifier,
    Outcome,
    Phase,
    References,
    Role,
    TaskSpec,
    TaskState,
    unique_evidence,
)

ROLE_TOOLS: dict[Role, tuple[str, ...]] = {
    "diagnosis": (
        "read_evidence",
        "read_contract",
        "read_source",
        "check_contract",
        "request_reproduction",
    ),
    "repair": ("read_evidence", "read_contract", "read_source"),
    "verification": (
        "read_evidence",
        "read_contract",
        "read_source",
        "check_contract",
        "request_reproduction",
    ),
}
type RoleOutput = ToolDecision | DiagnosisConclusion | RepairConclusion | VerificationConclusion


class PolicyError(ValueError):
    """Only static error codes are allowed across public boundaries."""


class EditableFile(Contract):
    path: RelativePath
    base_sha256: Digest


class AuthorizationContext(Contract):
    task_id: Identifier
    evidence_refs: References
    allowed_targets: Annotated[tuple[Digest, ...], Field(max_length=100)] = ()
    editable_files: Annotated[tuple[EditableFile, ...], Field(max_length=5)] = ()

    @model_validator(mode="after")
    def unique_grants(self) -> Self:
        unique_evidence(self.evidence_refs)
        if len(set(self.allowed_targets)) != len(self.allowed_targets):
            raise ValueError("duplicate_target")
        if len({entry.path for entry in self.editable_files}) != len(self.editable_files):
            raise ValueError("duplicate_edit_grant")
        return self


def authorize(task: TaskSpec, role: Role, output: RoleOutput, grants: AuthorizationContext) -> None:
    """Validates host registry membership, not physical artifacts or execution."""
    if grants.task_id != task.task_id or not set(grants.evidence_refs) <= set(task.evidence):
        raise PolicyError("TASK_SCOPE_MISMATCH")
    if isinstance(output, ToolDecision):
        request = output.request
        if (
            request.tool not in ROLE_TOOLS[role]
            or target_key(request) not in grants.allowed_targets
        ):
            raise PolicyError("PERMISSION_DENIED")
        if isinstance(request, ReadEvidence) and request.evidence_ref not in grants.evidence_refs:
            raise PolicyError("EVIDENCE_NOT_AUTHORIZED")
        return
    expected = {
        "diagnosis": DiagnosisConclusion,
        "repair": RepairConclusion,
        "verification": VerificationConclusion,
    }
    if not isinstance(output, expected[role]):
        raise PolicyError("ROLE_OUTPUT_MISMATCH")
    if not set(output.evidence_refs) <= set(grants.evidence_refs):
        raise PolicyError("EVIDENCE_NOT_AUTHORIZED")
    if isinstance(output, RepairConclusion):
        allowed = {(item.path, item.base_sha256) for item in grants.editable_files}
        if any((edit.path, edit.base_sha256) not in allowed for edit in output.edits):
            raise PolicyError("EDIT_NOT_AUTHORIZED")


def transition(
    state: TaskState, phase: Phase, *, expected_revision: int, outcome: Outcome | None = None
) -> TaskState:
    if type(expected_revision) is not int or not 0 <= expected_revision <= 1_000_000:
        raise PolicyError("INVALID_REVISION")
    if state.revision != expected_revision:
        raise PolicyError("STALE_VERSION")
    edges: dict[Phase, tuple[Phase, ...]] = {
        "queued": ("checking", "finished"),
        "checking": ("diagnosing", "finished"),
        "diagnosing": ("proposing", "reviewing", "finished"),
        "proposing": ("reviewing", "finished"),
        "reviewing": ("proposing", "finished"),
        "finished": (),
    }
    if phase not in edges[state.phase]:
        raise PolicyError("INVALID_TRANSITION")
    success_phase = {
        "check_complete": "checking",
        "diagnosis_complete": "reviewing",
        "proposal_only": "reviewing",
    }
    if outcome in success_phase and state.phase != success_phase[outcome]:
        raise PolicyError("PREMATURE_COMPLETION")
    try:
        return TaskState(
            task_id=state.task_id,
            intent=state.intent,
            phase=phase,
            revision=state.revision + 1,
            outcome=outcome,
        )
    except ValueError:
        raise PolicyError("INVALID_TRANSITION") from None
