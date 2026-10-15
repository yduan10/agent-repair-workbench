"""Atomic T05 admission, immutable execution identity and metadata-only oracle evidence."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Connection, select

from agent_workbench.candidate_execution.docker import verified_image
from agent_workbench.candidate_execution.models import OracleReport
from agent_workbench.candidate_execution.oracle import ORACLE_SHA256, SUITE_SHA256, verify_oracle
from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.schema import repair_comparison_attempts as attempts
from agent_workbench.run_store.schema import repair_comparisons as comparisons
from agent_workbench.run_store.schema import repair_execution_identities as identities
from agent_workbench.run_store.schema import repair_reproductions as reproductions
from agent_workbench.run_store.store import _uuid

from .comparisons import ComparisonStore
from .fencing import RepairFence
from .models import Mutation, RepairClaim, RepairTask, RequestRecord, Role, Tool
from .reproduction_models import (
    ReproductionMutation,
    ReproductionPlan,
    ReproductionRecord,
    result_outcome,
)
from .store import MAX_REQUESTS, _bytes, _load, _new, _permission, _validated


def _payload(plan: ReproductionPlan, role: Role) -> str:
    return digest(
        canonical(
            {
                "operation": "reproduction",
                "role": role,
                "tool": "T05",
                "plan": plan.model_dump(mode="json"),
            }
        )
    )


def verify_versions(plan: ReproductionPlan, baseline: SnapshotHandle, image_root: Path) -> bool:
    try:
        if baseline.ref != plan.baseline:
            return False
        SnapshotStore(baseline.root.parent).verify(baseline)
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


def _records(connection: Connection, task_id: str) -> dict[str, ReproductionRecord]:
    rows = (
        connection.execute(
            select(reproductions).where(reproductions.c.task_id == task_id).limit(MAX_REQUESTS + 1)
        )
        .mappings()
        .all()
    )
    if len(rows) > MAX_REQUESTS:
        raise StoreError("store_corrupt")
    records = {}
    for row in rows:
        record = _load(ReproductionRecord, row)
        if (
            record.plan.task_id != task_id
            or record.plan.request_id != row["request_id"]
            or record.plan.attempt_id != row["attempt_id"]
        ):
            raise StoreError("store_corrupt")
        records[record.plan.request_id] = record
    return records


def audit_reproductions(
    connection: Connection, task: RepairTask, requests: dict[str, RequestRecord]
) -> None:
    records = _records(connection, task.task_id)
    reqs = {k: r for k, r in requests.items() if r.operation == "reproduction"}
    if set(records) != set(reqs):
        raise StoreError("store_corrupt")
    expected: dict[str, tuple[str, str]] = {}
    for key, record in records.items():
        req, plan = reqs[key], record.plan
        if task.baseline != plan.baseline or req.payload_sha256 != _payload(plan, req.role):
            raise StoreError("store_corrupt")
        expected[plan.attempt_id] = ("reproduction", task.task_id + ":" + key)
        status = "pending" if record.status == "reserved" else "outcome_unknown"
        if record.report:
            outcome = result_outcome(
                record.report, record.versions_verified_after, baseline=record.plan.baseline
            )
            status = (
                "completed"
                if outcome == "observed_failure"
                else "outcome_unknown"
                if outcome == "outcome_unknown"
                else "failed"
            )
        if req.status != status:
            raise StoreError("store_corrupt")
    comparison_ids = list(
        connection.execute(
            select(comparisons.c.comparison_id).where(comparisons.c.task_id == task.task_id)
        ).scalars()
    )
    for row in connection.execute(
        select(attempts).where(attempts.c.comparison_id.in_(comparison_ids))
    ).mappings():
        if row["attempt_id"] in expected:
            raise StoreError("store_corrupt")
        expected[row["attempt_id"]] = ("comparison", row["comparison_id"])
    # Check both expected IDs and ownership: missing, reassigned and orphan identities fail.
    rows = (
        connection.execute(
            select(identities)
            .where(
                identities.c.attempt_id.in_(list(expected))
                | identities.c.owner_id.in_(comparison_ids)
                | identities.c.owner_id.like(task.task_id + ":%")
            )
            .limit(MAX_REQUESTS + 9)
        )
        .mappings()
        .all()
    )
    actual = {r["attempt_id"]: (r["kind"], r["owner_id"]) for r in rows}
    if actual != expected:
        raise StoreError("store_corrupt")


def _result(
    m: Mutation, r: ReproductionRecord, claim: RepairClaim | None = None
) -> ReproductionMutation:
    return ReproductionMutation(
        task=m.task,
        task_sha256=m.task_sha256,
        request=m.request,
        candidate=m.candidate,
        claim=claim,
        reproduction=r,
    )


class ReproductionStore(ComparisonStore):
    def get_reproduction(self, task_id: str, request_id: str) -> ReproductionRecord:
        with self._base._transaction() as connection:
            self._read(connection, _uuid(task_id))
            record = _records(connection, task_id).get(_uuid(request_id))
            if record is None:
                raise StoreError("reproduction_not_found")
            return record

    def reserve_tool(
        self,
        task_id: str,
        request_id: str,
        role: Role,
        tool: Tool,
        request_sha256: str,
        *,
        expected_revision: int,
        expected_sha256: str,
        fence: RepairFence,
    ) -> Mutation:
        if tool == "T05":
            raise StoreError("reproduction_reservation_required")
        return super().reserve_tool(
            task_id,
            request_id,
            role,
            tool,
            request_sha256,
            expected_revision=expected_revision,
            expected_sha256=expected_sha256,
            fence=fence,
        )

    def reserve_reproduction(
        self,
        plan: ReproductionPlan,
        *,
        role: Role,
        expected_revision: int,
        expected_sha256: str,
        fence: RepairFence,
        baseline: SnapshotHandle,
        image_root: Path,
    ) -> ReproductionMutation:
        plan = _validated(ReproductionPlan, plan)
        fence.require(self.directory, plan.task_id)
        with self._base._transaction(write=True) as connection:
            task, requests, _ = self._read(connection, plan.task_id)
            _permission(task, role, "T05")
            payload = _payload(plan, role)
            previous = requests.get(plan.request_id)
            if previous:
                if previous.operation != "reproduction" or previous.payload_sha256 != payload:
                    raise StoreError("request_conflict")
                return _result(
                    Mutation(task, digest(_bytes(task)), previous),
                    _records(connection, task.task_id)[plan.request_id],
                )
            self._cas(task, expected_revision, expected_sha256)
            if task.phase != "ready" or not task.usage.usage_complete:
                raise StoreError("request_pending")
            if len(requests) >= MAX_REQUESTS or task.usage.tool_calls >= task.budget.tool_calls:
                raise StoreError("budget_exceeded")
            now = self._now()
            if (
                now < task.started_at
                or (now - task.started_at).total_seconds() >= task.budget.timeout_seconds
            ):
                raise StoreError("deadline_exceeded")
            if task.baseline != plan.baseline:
                raise StoreError("baseline_binding")
            if not verify_versions(plan, baseline, image_root):
                raise StoreError("version_mismatch")
            token = secrets.token_hex(32)
            req = RequestRecord(
                request_id=plan.request_id,
                task_id=task.task_id,
                operation="reproduction",
                role=role,
                tool="T05",
                payload_sha256=payload,
                claim_sha256=digest(token.encode()),
            )
            record = ReproductionRecord(plan=plan, created_at=now)
            self._put_reproduction(connection, record, insert=True)
            new = _new(
                task,
                phase="tool_pending",
                usage=_new(task.usage, tool_calls=task.usage.tool_calls + 1),
            )
            result = self._commit(connection, task, new, "reserved", req, insert=True)
            return _result(result, record, RepairClaim(task.task_id, plan.request_id, token))

    def _put_reproduction(
        self, connection: Connection, record: ReproductionRecord, *, insert: bool = False
    ) -> None:
        p = record.plan
        self._put(
            connection,
            reproductions,
            record,
            dict(task_id=p.task_id, request_id=p.request_id, attempt_id=p.attempt_id),
            replace=not insert,
        )

    def finish_reproduction(
        self,
        claim: RepairClaim,
        report: OracleReport,
        *,
        expected_revision: int,
        expected_sha256: str,
        fence: RepairFence,
        baseline: SnapshotHandle,
        image_root: Path,
    ) -> ReproductionMutation:
        try:
            report = OracleReport.model_validate_json(report.model_dump_json())
        except (ValidationError, ValueError, AttributeError):
            raise StoreError("invalid_repair_input") from None
        fence.require(self.directory, _uuid(claim.task_id))
        with self._base._transaction(write=True) as connection:
            task, requests, _ = self._read(connection, claim.task_id)
            req = requests.get(claim.request_id)
            if (
                req is None
                or req.operation != "reproduction"
                or not secrets.compare_digest(req.claim_sha256, digest(claim.token.encode()))
            ):
                raise StoreError("claim_conflict")
            record = _records(connection, task.task_id)[req.request_id]
            if record.report is not None:
                if canonical(record.report.model_dump(mode="json")) != canonical(
                    report.model_dump(mode="json")
                ):
                    raise StoreError("report_conflict")
                return _result(Mutation(task, digest(_bytes(task)), req), record)
            self._cas(task, expected_revision, expected_sha256)
            if req.status != "pending" or record.status != "reserved":
                raise StoreError("claim_conflict")
            verified = verify_versions(record.plan, baseline, image_root)
            record = _new(
                record,
                status="finished",
                report=report,
                versions_verified_after=verified,
                finished_at=self._now(),
            )
            outcome = result_outcome(report, verified, baseline=record.plan.baseline)
            self._put_reproduction(connection, record)
            req = _new(
                req,
                status=(
                    "completed"
                    if outcome == "observed_failure"
                    else "outcome_unknown"
                    if outcome == "outcome_unknown"
                    else "failed"
                ),
                error_code=None if outcome == "observed_failure" else "TOOL_FAILED",
            )
            new = (
                _new(task, phase="ready")
                if outcome == "observed_failure"
                else _new(
                    task,
                    phase="finished",
                    outcome=outcome,
                    error_code="TOOL_FAILED",
                    finished_at=self._now(),
                )
            )
            return _result(self._commit(connection, task, new, "settled", req), record)

    def reconcile_reproduction(
        self, task_id: str, *, expected_revision: int, expected_sha256: str
    ) -> ReproductionMutation:
        with RepairFence(self.directory, _uuid(task_id)):
            with self._base._transaction(write=True) as connection:
                task, requests, _ = self._read(connection, task_id)
                self._cas(task, expected_revision, expected_sha256)
                req = next(
                    (
                        r
                        for r in requests.values()
                        if r.operation == "reproduction" and r.status == "pending"
                    ),
                    None,
                )
                if req is None:
                    raise StoreError("reproduction_not_pending")
                record = _new(
                    _records(connection, task_id)[req.request_id],
                    status="outcome_unknown",
                    finished_at=self._now(),
                )
                self._put_reproduction(connection, record)
                req = _new(req, status="outcome_unknown", error_code="INTERRUPTED")
                new = _new(
                    task,
                    phase="finished",
                    outcome="outcome_unknown",
                    error_code="INTERRUPTED",
                    finished_at=self._now(),
                )
                return _result(self._commit(connection, task, new, "reconciled", req), record)
