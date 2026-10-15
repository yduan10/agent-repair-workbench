"""Host-only frozen comparison. Admission must be persisted before calling this module.

No replay, retry, model command, or candidate-provided test report is accepted here.
The caller owns its lifetime fence and saves each result before advancing to the next slot.
"""

import math
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agent_workbench.candidate_execution.docker import verified_image
from agent_workbench.candidate_execution.models import OracleReport
from agent_workbench.candidate_execution.oracle import (
    ORACLE_SHA256,
    SUITE_SHA256,
    run_oracle,
    verify_oracle,
)
from agent_workbench.candidates.contracts import CandidateError, SnapshotRef
from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore
from agent_workbench.orchestration.contracts import Contract, Digest, Identifier, Version
from agent_workbench.repair_cases.bindings import validate_baseline_binding

Slot = Literal["baseline_wrong_type", "baseline_pass", "candidate_wrong_type", "candidate_pass"]
SLOTS: tuple[Slot, ...] = (
    "baseline_wrong_type",
    "baseline_pass",
    "candidate_wrong_type",
    "candidate_pass",
)
Outcome = Literal["candidate_verified", "rejected", "inconclusive", "cancelled", "outcome_unknown"]
Reason = Literal[
    "frozen_suite_passed",
    "candidate_failed",
    "baseline_not_reproduced",
    "execution_incomplete",
    "version_mismatch",
    "execution_cancelled",
    "cleanup_unconfirmed",
    "execution_unknown",
]


class ComparisonPlan(Contract):
    """Bound by the caller's durable T07 reservation, not writable by a model."""

    schema_version: Version = 1
    task_id: Identifier
    request_id: Identifier
    comparison_id: Identifier
    baseline: SnapshotRef
    candidate: SnapshotRef
    attempts: Annotated[tuple[Identifier, ...], Field(min_length=4, max_length=4)]
    suite_sha256: Digest
    oracle_sha256: Digest
    image_id: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    image_source_sha256: Digest

    @model_validator(mode="after")
    def bindings(self) -> Self:
        if (
            self.baseline.kind != "baseline"
            or self.candidate.kind != "candidate"
            or self.candidate.baseline_id != self.baseline.snapshot_id
            or self.candidate.baseline_tree_sha256 != self.baseline.tree_sha256
            or self.candidate.manifest_sha256 != self.baseline.manifest_sha256
            or len(set(self.attempts)) != 4
        ):
            raise ValueError("comparison_binding_mismatch")
        return self


class SlotResult(Contract):
    slot: Slot
    report: OracleReport


def decide(
    plan: ComparisonPlan, results: tuple[SlotResult, ...], versions_verified: bool
) -> tuple[Outcome, Reason]:
    """All assertions are about the fixed behavioral suite, not general program correctness."""
    if not versions_verified:
        return "inconclusive", "version_mismatch"
    try:
        profile = validate_baseline_binding(plan.baseline)
    except CandidateError:
        return "inconclusive", "version_mismatch"
    for item in results:
        report = item.report
        index = SLOTS.index(item.slot)
        snapshot = plan.baseline if index < 2 else plan.candidate
        scenario = "wrong_type" if index % 2 == 0 else "pass"
        if (
            report.attempt_id != plan.attempts[index]
            or report.snapshot_id != snapshot.snapshot_id
            or report.snapshot_tree_sha256 != snapshot.tree_sha256
            or report.snapshot_file_sha256 != snapshot.file_sha256
            or report.scenario != scenario
            or report.suite_sha256 != plan.suite_sha256
            or report.oracle_sha256 != plan.oracle_sha256
            or report.image_id != plan.image_id
            or report.image_source_sha256 != plan.image_source_sha256
        ):
            return "inconclusive", "version_mismatch"
        if report.cleanup == "unconfirmed":
            return "outcome_unknown", "cleanup_unconfirmed"
        if report.status == "outcome_unknown":
            return "outcome_unknown", "execution_unknown"
        if report.status == "cancelled":
            return "cancelled", "execution_cancelled"
        if (
            report.error is not None
            or report.cleanup != "removed"
            or not report.snapshot_verified_before
            or not report.snapshot_verified_after
            or any(step.status == "not_run" for step in report.steps)
            or report.status not in ("passed", "failed")
        ):
            return "inconclusive", "execution_incomplete"
    if tuple(item.slot for item in results) != SLOTS:
        return "inconclusive", "execution_incomplete"
    original, control, changed, regression = (item.report for item in results)
    expected_failure = {"valid_one", "valid_zero", "valid_negative"}
    if (
        original.status != "failed"
        or any(
            (step.status, step.code)
            != (
                ("failed", profile.failure_code)
                if step.name in expected_failure
                else ("passed", "ok")
            )
            for step in original.steps
        )
        or control.status != "passed"
    ):
        return "inconclusive", "baseline_not_reproduced"
    if changed.status != "passed" or regression.status != "passed":
        return "rejected", "candidate_failed"
    return "candidate_verified", "frozen_suite_passed"


class ComparisonReport(Contract):
    schema_version: Version = 1
    plan: ComparisonPlan
    results: Annotated[tuple[SlotResult, ...], Field(max_length=4)]
    versions_verified: bool
    outcome: Outcome
    reason: Reason
    accepted: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        # Existing nested Pydantic instances may have been mutated after validation.
        # Reparse at this public DTO boundary as well as in the factory.
        for item in self.results:
            OracleReport.model_validate_json(item.report.model_dump_json())
        # Partial results must be the completed prefix. Missing slots are never invented.
        if tuple(item.slot for item in self.results) != SLOTS[: len(self.results)]:
            raise ValueError("comparison_slot_mismatch")
        if (self.outcome, self.reason) != decide(self.plan, self.results, self.versions_verified):
            raise ValueError("comparison_verdict_mismatch")
        return self


def verify_versions(
    plan: ComparisonPlan, baseline: SnapshotHandle, candidate: SnapshotHandle, image_root: Path
) -> bool:
    try:
        if baseline.ref != plan.baseline or candidate.ref != plan.candidate:
            return False
        SnapshotStore(baseline.root.parent).verify(baseline)
        SnapshotStore(candidate.root.parent).verify(candidate)
        image = verified_image(image_root)
        return (
            verify_oracle()
            and plan.oracle_sha256 == ORACLE_SHA256
            and plan.suite_sha256 == SUITE_SHA256
            and plan.image_id == image.image_id
            and plan.image_source_sha256 == image.source_sha256
        )
    except (CandidateError, OSError, ValueError):
        return False


def make_report(
    plan: ComparisonPlan, results: tuple[SlotResult, ...], *, versions_verified: bool
) -> ComparisonReport:
    # Revalidate nested mutable OracleReports before deriving any trusted verdict.
    items = tuple(SlotResult.model_validate_json(item.model_dump_json()) for item in results)
    outcome, reason = decide(plan, items, versions_verified)
    return ComparisonReport(
        plan=plan,
        results=items,
        versions_verified=versions_verified,
        outcome=outcome,
        reason=reason,
    )


async def compare(
    plan: ComparisonPlan,
    baseline: SnapshotHandle,
    candidate: SnapshotHandle,
    *,
    image_root: Path,
    save_result: Callable[[SlotResult], Awaitable[None]],
    remaining_seconds: Callable[[], float],
) -> ComparisonReport:
    """Execute each already-admitted identity at most once in this invocation.

    Never call this again to resume a partial run. On crash/cancel, the durable owner
    reconciles admitted identities. Persistence failure propagates without another run.
    """
    plan = ComparisonPlan.model_validate_json(plan.model_dump_json())
    results: list[SlotResult] = []
    if not verify_versions(plan, baseline, candidate, image_root):
        return make_report(plan, (), versions_verified=False)
    for index, slot in enumerate(SLOTS):
        # Reserve cleanup time in the calling task's overall deadline.
        remaining = remaining_seconds()
        if not math.isfinite(remaining) or remaining < 16:
            break
        allowance = min(25.0, remaining - 15.0)
        report = await run_oracle(
            baseline if index < 2 else candidate,
            scenario="wrong_type" if index % 2 == 0 else "pass",
            attempt_id=plan.attempts[index],
            image_root=image_root,
            stage_timeout=min(3.0, allowance),
            total_timeout=allowance,
        )
        item = SlotResult(slot=slot, report=report)
        await save_result(item)
        results.append(item)
        if report.status in ("cancelled", "outcome_unknown", "inconclusive"):
            break
    return make_report(
        plan,
        tuple(results),
        versions_verified=verify_versions(plan, baseline, candidate, image_root),
    )
