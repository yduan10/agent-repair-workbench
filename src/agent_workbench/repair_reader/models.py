"""Explicit web DTOs. Stored verdicts and currently revalidated verdicts are separate."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from agent_workbench.analysis_store.models import ErrorCode
from agent_workbench.candidate_execution.compare import SLOTS, Reason, Slot
from agent_workbench.candidate_execution.compare import Outcome as ComparisonOutcome
from agent_workbench.candidate_execution.models import OracleStep
from agent_workbench.candidates.contracts import SafeDiff
from agent_workbench.orchestration.contracts import (
    Budget,
    Contract,
    Digest,
    Identifier,
    Usage,
    Version,
)
from agent_workbench.repair_cases.profiles import RepairCaseId
from agent_workbench.repair_store.models import Outcome


class TaskView(Contract):
    task_id: Identifier
    case_id: RepairCaseId
    source_analysis_id: Identifier | None
    mode: Literal["single_role", "three_role"]
    phase: Literal[
        "ready", "model_pending", "tool_pending", "candidate_preparing", "comparing", "finished"
    ]
    recorded_outcome: Outcome | None
    error_code: ErrorCode | None
    revision: Annotated[int, Field(ge=0, lt=256)]
    sha256: Digest
    started_at: AwareDatetime
    finished_at: AwareDatetime | None
    budget: Budget
    usage: Usage
    candidate_count: Annotated[int, Field(ge=0, le=2)]
    cost_amount: None = None

    @model_validator(mode="after")
    def terminal_shape(self) -> Self:
        if (self.phase == "finished") != (self.recorded_outcome is not None) or (
            (self.phase == "finished") != (self.finished_at is not None)
        ):
            raise ValueError("terminal_mismatch")
        return self


class CandidateView(Contract):
    candidate_id: Identifier
    sequence: Annotated[int, Field(ge=1, le=2)]
    status: Literal["preparing", "committed", "failed", "outcome_unknown"]
    snapshot_status: Literal["verified", "unavailable", "not_created"]
    snapshot_sha256: Digest | None
    error_code: ErrorCode | None
    created_at: AwareDatetime
    finished_at: AwareDatetime | None


class SlotView(Contract):
    slot: Slot
    status: Literal["passed", "failed", "inconclusive", "cancelled", "outcome_unknown"]
    cleanup: Literal["not_created", "removed", "unconfirmed"]
    steps: Annotated[tuple[OracleStep, ...], Field(min_length=8, max_length=8)]


class ComparisonView(Contract):
    schema_version: Version = 1
    task_id: Identifier
    comparison_id: Identifier
    candidate_id: Identifier
    status: Literal["reserved", "finished", "outcome_unknown"]
    verification: Literal["verified", "unavailable", "not_finished"]
    recorded_outcome: ComparisonOutcome | None
    current_outcome: ComparisonOutcome | None
    reason: Reason | None
    unavailable_reason: Literal["artifact_or_version_mismatch"] | None
    suite_sha256: Digest
    oracle_sha256: Digest
    created_at: AwareDatetime
    finished_at: AwareDatetime | None
    slots: Annotated[tuple[SlotView, ...], Field(max_length=4)]
    accepted: Literal[False] = False

    @model_validator(mode="after")
    def current_verdict(self) -> Self:
        if tuple(item.slot for item in self.slots) != SLOTS[: len(self.slots)]:
            raise ValueError("slot_order")
        if self.verification == "unavailable":
            if (
                self.current_outcome is not None
                or self.reason is not None
                or self.slots
                or (self.unavailable_reason is None)
            ):
                raise ValueError("unverified_verdict")
        elif self.unavailable_reason is not None:
            raise ValueError("unexpected_unavailable_reason")
        elif self.verification == "not_finished":
            if (
                self.status == "finished"
                or self.current_outcome is not None
                or self.reason is not None
            ):
                raise ValueError("unfinished_verdict")
        elif (
            self.status != "finished"
            or self.current_outcome is None
            or (self.current_outcome != self.recorded_outcome or self.reason is None)
        ):
            raise ValueError("current_verdict_mismatch")
        return self


class RepairList(Contract):
    schema_version: Literal[2] = 2
    repairs: Annotated[tuple[TaskView, ...], Field(max_length=50)]


class RepairDetail(Contract):
    schema_version: Literal[2] = 2
    task: TaskView
    candidates: Annotated[tuple[CandidateView, ...], Field(max_length=2)]
    comparisons: Annotated[tuple[ComparisonView, ...], Field(max_length=2)]


class CandidateDiff(Contract):
    schema_version: Version = 1
    task_id: Identifier
    candidate_id: Identifier
    verification: Literal["verified"] = "verified"
    diff: SafeDiff

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.candidate_id != self.diff.candidate.snapshot_id:
            raise ValueError("candidate_binding")
        return self
