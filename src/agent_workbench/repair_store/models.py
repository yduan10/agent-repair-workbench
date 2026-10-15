"""Versioned bounded metadata. Claim tokens and model text are never DTO fields."""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from agent_workbench.analysis_store.models import ErrorCode
from agent_workbench.candidates.contracts import SnapshotRef
from agent_workbench.orchestration.contracts import (
    Budget,
    Contract,
    Digest,
    Identifier,
    Usage,
    Version,
)

Role = Literal["single", "diagnosis", "repair", "verification"]
Tool = Literal["T01", "T02", "T03", "T04", "T05", "T06", "T07"]
Outcome = Literal[
    "failed",
    "cancelled",
    "budget_exceeded",
    "outcome_unknown",
    "inconclusive",
    "candidate_verified",
]
Status = Literal["pending", "completed", "failed", "outcome_unknown"]
Revision = Annotated[int, Field(ge=0, lt=256)]
Tokens = Annotated[int, Field(ge=0, le=2_000_000)]


class RepairTask(Contract):
    schema_version: Version = 1
    task_id: Identifier
    source_analysis_id: Identifier | None = None
    baseline: SnapshotRef
    mode: Literal["single_role", "three_role"]
    revision: Revision = 0
    phase: Literal[
        "ready", "model_pending", "tool_pending", "candidate_preparing", "comparing", "finished"
    ] = "ready"
    outcome: Outcome | None = None
    error_code: ErrorCode | None = None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    budget: Budget
    usage: Usage = Usage()
    candidate_count: Annotated[int, Field(ge=0, le=2)] = 0
    model_config_sha256: Digest | None = None
    cost_amount: None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.baseline.kind != "baseline":
            raise ValueError("baseline_required")
        if (self.phase == "finished") != (self.outcome is not None) or (
            (self.phase == "finished") != (self.finished_at is not None)
        ):
            raise ValueError("terminal_mismatch")
        if any(
            t is not None and t.utcoffset() != timedelta(0)
            for t in (self.started_at, self.finished_at)
        ):
            raise ValueError("utc_required")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("time_order")
        u, b = self.usage, self.budget
        if (
            u.model_calls > b.model_calls
            or u.tool_calls > b.tool_calls
            or self.candidate_count > b.candidates
            or u.known_input_tokens + u.known_output_tokens + u.reserved_tokens > b.total_tokens
        ):
            raise ValueError("budget_exceeded")
        if u.model_calls and self.model_config_sha256 is None:
            raise ValueError("model_provenance_required")
        return self


class RequestRecord(Contract):
    """Private ledger record; expose curated events rather than this DTO through an API."""

    request_id: Identifier
    task_id: Identifier
    operation: Literal["model", "tool", "candidate", "comparison", "reproduction"]
    role: Role
    tool: Tool | None = None
    payload_sha256: Digest
    claim_sha256: Digest
    status: Status = "pending"
    input_reserved: Tokens = 0
    output_reserved: Annotated[int, Field(ge=0, le=32768)] = 0
    reservation_sha256: Digest | None = None
    known_input_tokens: Tokens | None = None
    known_output_tokens: Tokens | None = None
    candidate_id: Identifier | None = None
    error_code: ErrorCode | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.operation == "model":
            if (
                self.tool is not None
                or self.candidate_id is not None
                or self.reservation_sha256 is None
                or self.output_reserved < 1
            ):
                raise ValueError("model_shape")
            known = self.known_input_tokens is not None and self.known_output_tokens is not None
            if (self.status in ("completed", "failed")) != known:
                raise ValueError("usage_shape")
            if (self.known_input_tokens is None) != (self.known_output_tokens is None):
                raise ValueError("partial_usage")
            if (
                self.known_input_tokens is not None
                and self.known_output_tokens is not None
                and (
                    self.known_input_tokens > self.input_reserved
                    or self.known_output_tokens > self.output_reserved
                )
            ):
                raise ValueError("usage_bound")
        elif any(
            (
                self.input_reserved,
                self.output_reserved,
                self.reservation_sha256 is not None,
                self.known_input_tokens is not None,
                self.known_output_tokens is not None,
            )
        ):
            raise ValueError("unexpected_usage")
        if self.operation == "reproduction" and (
            self.tool != "T05" or self.candidate_id is not None
        ):
            raise ValueError("reproduction_shape")
        if self.operation == "tool" and (
            self.tool not in ("T01", "T02", "T03", "T04", "T05") or self.candidate_id is not None
        ):
            raise ValueError("tool_shape")
        if self.operation == "candidate" and (self.tool != "T06" or self.candidate_id is None):
            raise ValueError("candidate_shape")
        if self.operation == "comparison" and (self.tool != "T07" or self.candidate_id is None):
            raise ValueError("comparison_shape")
        return self


class CandidateRecord(Contract):
    schema_version: Version = 1
    task_id: Identifier
    candidate_id: Identifier
    request_id: Identifier
    sequence: Annotated[int, Field(ge=1, le=2)]
    owner_role: Literal["repair", "single"]
    status: Literal["preparing", "committed", "failed", "outcome_unknown"] = "preparing"
    expected_baseline_hash: Digest
    expected_file_hash: Digest
    patch_sha256: Digest
    snapshot: SnapshotRef | None = None
    error_code: ErrorCode | None = None
    created_at: AwareDatetime
    finished_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.status == "committed") != (self.snapshot is not None):
            raise ValueError("snapshot_state")
        if (self.status == "preparing") != (self.finished_at is None):
            raise ValueError("candidate_time")
        if self.snapshot and (
            self.snapshot.kind != "candidate"
            or self.snapshot.snapshot_id != self.candidate_id
            or self.snapshot.baseline_tree_sha256 != self.expected_baseline_hash
            or self.snapshot.patch_sha256 != self.patch_sha256
        ):
            raise ValueError("snapshot_binding")
        if self.finished_at and self.finished_at < self.created_at:
            raise ValueError("time_order")
        return self


class RepairEvent(Contract):
    schema_version: Version = 1
    task_id: Identifier
    revision: Revision
    kind: Literal["created", "reserved", "settled", "finished", "reconciled", "comparison_slot"]
    task_sha256: Digest
    at: AwareDatetime
    request: RequestRecord | None = None
    candidate: CandidateRecord | None = None


@dataclass(frozen=True)
class RepairClaim:
    task_id: str
    request_id: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class Mutation:
    task: RepairTask
    task_sha256: str
    request: RequestRecord | None = None
    candidate: CandidateRecord | None = None
    claim: RepairClaim | None = None
