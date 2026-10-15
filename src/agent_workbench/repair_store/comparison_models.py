"""Persisted host comparison evidence. No model-supplied verdict field is accepted."""

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from agent_workbench.candidate_execution.compare import (
    SLOTS,
    ComparisonPlan,
    ComparisonReport,
    SlotResult,
)
from agent_workbench.orchestration.contracts import Contract, Version

from .models import Mutation


class ComparisonRecord(Contract):
    schema_version: Version = 1
    plan: ComparisonPlan
    status: Literal["reserved", "finished", "outcome_unknown"] = "reserved"
    results: Annotated[tuple[SlotResult, ...], Field(max_length=4)] = ()
    report: ComparisonReport | None = None
    versions_verified_before: Literal[True] = True
    created_at: AwareDatetime
    finished_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if tuple(item.slot for item in self.results) != SLOTS[: len(self.results)]:
            raise ValueError("slot_prefix")
        if (self.status == "reserved") != (self.finished_at is None):
            raise ValueError("terminal_time")
        if (self.status == "finished") != (self.report is not None):
            raise ValueError("terminal_report")
        if self.report is not None and (
            self.report.plan != self.plan or self.report.results != self.results
        ):
            raise ValueError("report_binding")
        if self.finished_at and self.finished_at < self.created_at:
            raise ValueError("time_order")
        return self


@dataclass(frozen=True)
class AttemptState:
    attempt_id: str
    slot: str
    status: str
    report_sha256: str | None


@dataclass(frozen=True)
class ComparisonMutation(Mutation):
    comparison: ComparisonRecord | None = None
