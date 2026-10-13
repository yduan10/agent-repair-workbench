"""Shared immutable contracts. No raw model text is persisted in these models."""

from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Version = Annotated[int, Field(strict=True, ge=1, le=1)]
Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Name = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")]
Count = Annotated[int, Field(ge=0, le=1_000_000)]
Role = Literal["diagnosis", "repair", "verification"]
Intent = Literal["check_only", "diagnose", "propose_repair"]
SourceKind = Literal["synthetic", "public_historical"]
Reason = Literal[
    "evidence_missing",
    "contract_mismatch",
    "serialization_mismatch",
    "unsupported",
    "proposal_requires_execution",
]
Phase = Literal["queued", "checking", "diagnosing", "proposing", "reviewing", "finished"]
Outcome = Literal[
    "check_complete",
    "diagnosis_complete",
    "proposal_only",
    "inconclusive",
    "cancelled",
    "failed",
    "budget_exceeded",
    "outcome_unknown",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class EvidenceRef(Contract):
    evidence_id: Identifier
    sha256: Digest


References = Annotated[tuple[EvidenceRef, ...], Field(max_length=32)]


def unique_evidence(refs: tuple[EvidenceRef, ...]) -> None:
    if len({ref.evidence_id for ref in refs}) != len(refs):
        raise ValueError("duplicate_evidence")


class Budget(Contract):
    total_tokens: Annotated[int, Field(ge=1, le=1_000_000)]
    output_tokens: Annotated[int, Field(ge=1, le=32768)]
    model_calls: Annotated[int, Field(ge=1, le=12)] = 12
    tool_calls: Annotated[int, Field(ge=1, le=20)] = 20
    candidates: Annotated[int, Field(ge=1, le=2)] = 2
    timeout_seconds: Annotated[int, Field(ge=1, le=600)] = 600

    @model_validator(mode="after")
    def output_fits(self) -> Self:
        if self.output_tokens > self.total_tokens:
            raise ValueError("output_budget_exceeds_total")
        return self


class TaskSpec(Contract):
    schema_version: Version = 1
    task_id: Identifier
    intent: Intent
    source_kind: SourceKind
    budget: Budget
    evidence: Annotated[tuple[EvidenceRef, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def unique_refs(self) -> Self:
        unique_evidence(self.evidence)
        return self


class TaskState(Contract):
    task_id: Identifier
    intent: Intent
    phase: Phase = "queued"
    revision: Count = 0
    outcome: Outcome | None = None

    @model_validator(mode="after")
    def consistent_phase(self) -> Self:
        if (self.phase == "finished") != (self.outcome is not None):
            raise ValueError("terminal_outcome_mismatch")
        if self.intent == "check_only" and self.phase not in ("queued", "checking", "finished"):
            raise ValueError("intent_phase_mismatch")
        if self.intent == "diagnose" and self.phase == "proposing":
            raise ValueError("intent_phase_mismatch")
        expected = {
            "check_complete": "check_only",
            "diagnosis_complete": "diagnose",
            "proposal_only": "propose_repair",
        }
        if self.outcome in expected and self.intent != expected[self.outcome]:
            raise ValueError("intent_outcome_mismatch")
        if self.phase == "queued" and self.revision != 0:
            raise ValueError("initial_revision_mismatch")
        if self.phase != "queued" and self.revision == 0:
            raise ValueError("advanced_revision_required")
        return self


class Usage(Contract):
    model_calls: Annotated[int, Field(ge=0, le=12)] = 0
    tool_calls: Annotated[int, Field(ge=0, le=20)] = 0
    reserved_tokens: Count = 0
    known_input_tokens: Count = 0
    known_output_tokens: Count = 0
    usage_complete: bool = True

    @model_validator(mode="after")
    def reservations(self) -> Self:
        if self.usage_complete != (self.reserved_tokens == 0):
            raise ValueError("usage_reservation_mismatch")
        if not self.model_calls and (
            self.reserved_tokens or self.known_input_tokens or self.known_output_tokens
        ):
            raise ValueError("tokens_without_model_call")
        return self


class AnalysisSummary(Contract):
    schema_version: Version = 1
    task_id: Identifier
    summary_revision: Count = 0
    source_kind: SourceKind
    state: TaskState
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    budget: Budget
    usage: Usage
    evidence_refs: References
    execution_record_ids: Annotated[tuple[Identifier, ...], Field(max_length=20)] = ()
    proposal_count: Annotated[int, Field(ge=0, le=2)] = 0
    model_config_sha256: Digest | None = None
    cost_amount: None = None

    @model_validator(mode="after")
    def consistency(self) -> Self:
        unique_evidence(self.evidence_refs)
        if self.task_id != self.state.task_id or self.summary_revision < self.state.revision:
            raise ValueError("summary_state_mismatch")
        if self.state.phase == "queued" and self.summary_revision != 0:
            raise ValueError("initial_summary_revision_mismatch")
        if self.started_at.utcoffset() != timedelta(0) or (
            self.finished_at and self.finished_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("utc_required")
        if (self.state.phase == "finished") != (self.finished_at is not None):
            raise ValueError("summary_terminal_time_mismatch")
        if self.finished_at and self.finished_at < self.started_at:
            raise ValueError("invalid_time_order")
        usage = self.usage
        if (
            usage.model_calls > self.budget.model_calls
            or usage.tool_calls > self.budget.tool_calls
            or self.proposal_count > self.budget.candidates
            or usage.known_input_tokens + usage.known_output_tokens + usage.reserved_tokens
            > self.budget.total_tokens
        ):
            raise ValueError("budget_exceeded")
        if bool(usage.model_calls) != (self.model_config_sha256 is not None):
            raise ValueError("model_provenance_mismatch")
        if len(set(self.execution_record_ids)) != len(self.execution_record_ids):
            raise ValueError("duplicate_execution_record")
        return self
