"""Host-authored T05 identities; a baseline reproduction never verifies a candidate."""

from dataclasses import dataclass
from typing import Annotated, Literal, Self
from uuid import UUID, uuid5

from pydantic import AwareDatetime, Field, model_validator

from agent_workbench.candidate_execution.models import OracleReport
from agent_workbench.candidates.contracts import CandidateError, SnapshotRef
from agent_workbench.orchestration.contracts import Contract, Digest, Identifier, Version
from agent_workbench.repair_cases.bindings import validate_baseline_binding

from .models import Mutation


def reproduction_id(task_id: str, request_id: str) -> str:
    return str(uuid5(UUID(task_id), "p006:T05:v1:" + str(UUID(request_id))))


class ReproductionPlan(Contract):
    schema_version: Version = 1
    task_id: Identifier
    request_id: Identifier
    attempt_id: Identifier
    baseline: SnapshotRef
    scenario: Literal["wrong_type"] = "wrong_type"
    suite_sha256: Digest
    oracle_sha256: Digest
    image_id: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    image_source_sha256: Digest

    @model_validator(mode="after")
    def binding(self) -> Self:
        if self.baseline.kind != "baseline" or self.attempt_id != reproduction_id(
            self.task_id, self.request_id
        ):
            raise ValueError("reproduction_binding")
        return self


def report_bound(plan: ReproductionPlan, report: OracleReport) -> bool:
    return (
        report.attempt_id == plan.attempt_id
        and report.snapshot_id == plan.baseline.snapshot_id
        and report.snapshot_tree_sha256 == plan.baseline.tree_sha256
        and report.snapshot_file_sha256 == plan.baseline.file_sha256
        and report.scenario == plan.scenario
        and report.suite_sha256 == plan.suite_sha256
        and report.oracle_sha256 == plan.oracle_sha256
        and report.image_id == plan.image_id
        and report.image_source_sha256 == plan.image_source_sha256
    )


def result_outcome(report: OracleReport, versions_verified: bool, *, baseline: SnapshotRef) -> str:
    if report.cleanup == "unconfirmed" or report.status == "outcome_unknown":
        return "outcome_unknown"
    if report.status == "cancelled":
        return "cancelled"
    if not versions_verified or report.status == "inconclusive":
        return "inconclusive"
    try:
        report = OracleReport.model_validate_json(report.model_dump_json())
        profile = validate_baseline_binding(baseline)
    except (ValueError, CandidateError):
        return "inconclusive"
    if (
        report.snapshot_id != baseline.snapshot_id
        or report.snapshot_tree_sha256 != baseline.tree_sha256
        or report.snapshot_file_sha256 != baseline.file_sha256
        or report.scenario != "wrong_type"
        or report.error is not None
        or not report.snapshot_verified_before
        or not report.snapshot_verified_after
        or report.cleanup != "removed"
        or report.status != "failed"
        or any(
            (step.status, step.code)
            != (
                ("failed", profile.failure_code)
                if step.name in ("valid_one", "valid_zero", "valid_negative")
                else ("passed", "ok")
            )
            for step in report.steps
        )
    ):
        return "inconclusive"
    # A host-observed baseline failure is evidence, not a successful candidate verdict.
    return "observed_failure"


class ReproductionRecord(Contract):
    schema_version: Version = 1
    plan: ReproductionPlan
    status: Literal["reserved", "finished", "outcome_unknown"] = "reserved"
    report: OracleReport | None = None
    versions_verified_after: bool = False
    created_at: AwareDatetime
    finished_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.status == "reserved") != (self.finished_at is None):
            raise ValueError("terminal_time")
        if (self.status == "finished") != (self.report is not None):
            raise ValueError("terminal_report")
        if self.report:
            validated = OracleReport.model_validate_json(self.report.model_dump_json())
            if not report_bound(self.plan, validated):
                raise ValueError("report_binding")
        if self.finished_at and self.finished_at < self.created_at:
            raise ValueError("time_order")
        if self.status != "finished" and self.versions_verified_after:
            raise ValueError("version_state")
        return self


@dataclass(frozen=True)
class ReproductionMutation(Mutation):
    reproduction: ReproductionRecord | None = None
