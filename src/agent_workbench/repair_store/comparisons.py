"""T07 durable identities and verdicts derived only from stored host oracle results."""

from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy import Connection, select, update

from agent_workbench.candidate_execution.compare import (
    SLOTS,
    ComparisonPlan,
    SlotResult,
    make_report,
    verify_versions,
)
from agent_workbench.candidates.snapshots import SnapshotHandle
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.schema import repair_comparison_attempts as attempts
from agent_workbench.run_store.schema import repair_comparisons as comparisons
from agent_workbench.run_store.schema import repair_events
from agent_workbench.run_store.store import _uuid

from .comparison_models import AttemptState, ComparisonMutation, ComparisonRecord
from .fencing import RepairFence
from .models import (
    CandidateRecord,
    Mutation,
    RepairClaim,
    RepairEvent,
    RepairTask,
    RequestRecord,
    Role,
)
from .store import MAX_REQUESTS, RepairStore, _bytes, _load, _new, _permission, _validated


def _payload(plan: ComparisonPlan, role: Role) -> str:
    return digest(
        canonical(
            {
                "operation": "comparison",
                "role": role,
                "tool": "T07",
                "plan": plan.model_dump(mode="json"),
            }
        )
    )


def _bound(plan: ComparisonPlan, item: SlotResult, index: int) -> bool:
    report = item.report
    snapshot = plan.baseline if index < 2 else plan.candidate
    return (
        item.slot == SLOTS[index]
        and report.attempt_id == plan.attempts[index]
        and report.snapshot_id == snapshot.snapshot_id
        and report.snapshot_tree_sha256 == snapshot.tree_sha256
        and report.snapshot_file_sha256 == snapshot.file_sha256
        and report.scenario == ("wrong_type" if index % 2 == 0 else "pass")
        and report.suite_sha256 == plan.suite_sha256
        and report.oracle_sha256 == plan.oracle_sha256
        and report.image_id == plan.image_id
        and report.image_source_sha256 == plan.image_source_sha256
    )


def _records(connection: Connection, task_id: str) -> dict[str, ComparisonRecord]:
    rows = (
        connection.execute(select(comparisons).where(comparisons.c.task_id == task_id).limit(3))
        .mappings()
        .all()
    )
    if len(rows) > 2:
        raise StoreError("store_corrupt")
    result = {}
    for row in rows:
        record = _load(ComparisonRecord, row)
        plan = record.plan
        if (
            plan.task_id != task_id
            or plan.comparison_id != row["comparison_id"]
            or plan.request_id != row["request_id"]
            or plan.candidate.snapshot_id != row["candidate_id"]
        ):
            raise StoreError("store_corrupt")
        result[plan.request_id] = record
    return result


def audit_comparisons(
    connection: Connection,
    task: RepairTask,
    requests: dict[str, RequestRecord],
    candidates: dict[str, CandidateRecord],
) -> None:
    """Same transaction as RepairStore._read; compare all four registered identities."""
    records = _records(connection, task.task_id)
    comparison_requests = {k: r for k, r in requests.items() if r.operation == "comparison"}
    if set(records) != set(comparison_requests):
        raise StoreError("store_corrupt")
    slot_counts: dict[str, int] = {}
    active = None
    for row in connection.execute(
        select(repair_events)
        .where(repair_events.c.task_id == task.task_id)
        .order_by(repair_events.c.revision)
    ).mappings():
        event = _load(RepairEvent, row)
        if event.request and event.request.operation == "comparison":
            active = event.request.request_id if event.request.status == "pending" else None
        if event.kind == "comparison_slot":
            if active is None:
                raise StoreError("store_corrupt")
            slot_counts[active] = slot_counts.get(active, 0) + 1
    verified = 0
    for key, record in records.items():
        plan, req = record.plan, comparison_requests[key]
        candidate = candidates.get(plan.candidate.snapshot_id)
        if (
            candidate is None
            or candidate.status != "committed"
            or candidate.snapshot != plan.candidate
            or task.baseline != plan.baseline
            or req.candidate_id != plan.candidate.snapshot_id
            or req.payload_sha256 != _payload(plan, req.role)
            or slot_counts.get(key, 0) != len(record.results)
        ):
            raise StoreError("store_corrupt")
        rows = (
            connection.execute(
                select(attempts)
                .where(attempts.c.comparison_id == plan.comparison_id)
                .order_by(attempts.c.slot_index)
                .limit(5)
            )
            .mappings()
            .all()
        )
        if len(rows) != 4:
            raise StoreError("store_corrupt")
        for index, row in enumerate(rows):
            item = record.results[index] if index < len(record.results) else None
            expected_status = (
                "reported"
                if item
                else ("unknown" if record.status == "outcome_unknown" else "admitted")
            )
            expected_sha = digest(_bytes(item)) if item else None
            if (
                row["attempt_id"] != plan.attempts[index]
                or row["slot_index"] != index
                or row["status"] != expected_status
                or row["report_sha256"] != expected_sha
                or (item is not None and not _bound(plan, item, index))
            ):
                raise StoreError("store_corrupt")
        expected = "pending" if record.status == "reserved" else "outcome_unknown"
        if record.report:
            expected = (
                "completed"
                if record.report.outcome in ("candidate_verified", "rejected")
                else ("outcome_unknown" if record.report.outcome == "outcome_unknown" else "failed")
            )
            if record.report.outcome == "candidate_verified":
                verified += 1
        if req.status != expected:
            raise StoreError("store_corrupt")
    if (task.outcome == "candidate_verified") != (verified == 1) or verified > 1:
        raise StoreError("store_corrupt")


def _result(
    mutation: Mutation, record: ComparisonRecord, claim: RepairClaim | None = None
) -> ComparisonMutation:
    return ComparisonMutation(
        task=mutation.task,
        task_sha256=mutation.task_sha256,
        request=mutation.request,
        candidate=mutation.candidate,
        claim=claim,
        comparison=record,
    )


class ComparisonStore(RepairStore):
    def read_detail(
        self, task_id: str
    ) -> tuple[Mutation, list[CandidateRecord], list[ComparisonRecord]]:
        """Read task, candidates and comparisons from the same audited DB snapshot."""
        with self._base._transaction() as connection:
            task, _, candidates = self._read(connection, _uuid(task_id))
            comparisons = _records(connection, task_id)
            return (
                Mutation(task, digest(_bytes(task))),
                sorted(candidates.values(), key=lambda c: c.sequence),
                sorted(comparisons.values(), key=lambda c: c.created_at),
            )

    def comparisons(self, task_id: str) -> list[ComparisonRecord]:
        with self._base._transaction() as connection:
            self._read(connection, _uuid(task_id))
            return sorted(_records(connection, task_id).values(), key=lambda r: r.created_at)

    def comparison(self, task_id: str, comparison_id: str) -> ComparisonRecord:
        _uuid(comparison_id)
        for record in self.comparisons(task_id):
            if record.plan.comparison_id == comparison_id:
                return record
        raise StoreError("comparison_not_found")

    def get_comparison(self, task_id: str, request_id: str) -> ComparisonRecord:
        """Historical metadata; UI verified labels must use read_verified_comparison."""
        with self._base._transaction() as connection:
            self._read(connection, _uuid(task_id))
            record = _records(connection, task_id).get(_uuid(request_id))
            if record is None:
                raise StoreError("comparison_not_found")
            return record

    def admitted_attempts(self, task_id: str, request_id: str) -> tuple[AttemptState, ...]:
        with self._base._transaction() as connection:
            self._read(connection, _uuid(task_id))
            record = _records(connection, task_id).get(_uuid(request_id))
            if record is None:
                raise StoreError("comparison_not_found")
            rows = (
                connection.execute(
                    select(attempts)
                    .where(attempts.c.comparison_id == record.plan.comparison_id)
                    .order_by(attempts.c.slot_index)
                )
                .mappings()
                .all()
            )
            return tuple(
                AttemptState(
                    row["attempt_id"], SLOTS[row["slot_index"]], row["status"], row["report_sha256"]
                )
                for row in rows
            )

    def read_verified_comparison(
        self,
        task_id: str,
        request_id: str,
        *,
        baseline: SnapshotHandle,
        candidate: SnapshotHandle,
        image_root: Path,
    ) -> ComparisonRecord:
        record = self.get_comparison(task_id, request_id)
        if not verify_versions(record.plan, baseline, candidate, image_root):
            raise StoreError("version_mismatch")
        return record

    def reserve_comparison(
        self,
        plan: ComparisonPlan,
        *,
        role: Role,
        expected_revision: int,
        expected_sha256: str,
        fence: RepairFence,
        baseline: SnapshotHandle,
        candidate: SnapshotHandle,
        image_root: Path,
    ) -> ComparisonMutation:
        plan = _validated(ComparisonPlan, plan)
        fence.require(self.directory, plan.task_id)
        with self._base._transaction(write=True) as connection:
            task, requests, candidates = self._read(connection, plan.task_id)
            _permission(task, role, "T07")
            previous = requests.get(plan.request_id)
            payload_hash = _payload(plan, role)
            if previous:
                if previous.operation != "comparison" or previous.payload_sha256 != payload_hash:
                    raise StoreError("request_conflict")
                record = _records(connection, task.task_id)[plan.request_id]
                return _result(Mutation(task, digest(_bytes(task)), previous), record)
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
            committed = candidates.get(plan.candidate.snapshot_id)
            if (
                committed is None
                or committed.status != "committed"
                or committed.snapshot != plan.candidate
                or task.baseline != plan.baseline
            ):
                raise StoreError("candidate_binding")
            if connection.execute(
                select(comparisons.c.comparison_id).where(
                    (comparisons.c.candidate_id == plan.candidate.snapshot_id)
                    | (comparisons.c.comparison_id == plan.comparison_id)
                )
            ).first():
                raise StoreError("comparison_conflict")
            if connection.execute(
                select(attempts.c.attempt_id).where(attempts.c.attempt_id.in_(plan.attempts))
            ).first():
                raise StoreError("attempt_conflict")
            if not verify_versions(plan, baseline, candidate, image_root):
                raise StoreError("version_mismatch")
            token = secrets.token_hex(32)
            req = RequestRecord(
                request_id=plan.request_id,
                task_id=task.task_id,
                operation="comparison",
                role=role,
                tool="T07",
                payload_sha256=payload_hash,
                claim_sha256=digest(token.encode()),
                candidate_id=plan.candidate.snapshot_id,
            )
            record = ComparisonRecord(plan=plan, created_at=now)
            self._put_comparison(connection, record, insert=True)
            for index, attempt_id in enumerate(plan.attempts):
                connection.execute(
                    attempts.insert().values(
                        attempt_id=attempt_id,
                        comparison_id=plan.comparison_id,
                        slot_index=index,
                        status="admitted",
                        report_sha256=None,
                    )
                )
            new = _new(
                task,
                phase="comparing",
                usage=_new(task.usage, tool_calls=task.usage.tool_calls + 1),
            )
            result = self._commit(connection, task, new, "reserved", req, insert=True)
            return _result(result, record, RepairClaim(task.task_id, plan.request_id, token))

    def _put_comparison(
        self, connection: Connection, record: ComparisonRecord, *, insert: bool = False
    ) -> None:
        plan = record.plan
        self._put(
            connection,
            comparisons,
            record,
            dict(
                comparison_id=plan.comparison_id,
                task_id=plan.task_id,
                request_id=plan.request_id,
                candidate_id=plan.candidate.snapshot_id,
            ),
            replace=not insert,
        )

    def _owned(
        self, connection: Connection, claim: RepairClaim, fence: RepairFence
    ) -> tuple[RepairTask, RequestRecord, ComparisonRecord]:
        fence.require(self.directory, _uuid(claim.task_id))
        task, requests, _ = self._read(connection, claim.task_id)
        req = requests.get(claim.request_id)
        if (
            req is None
            or req.operation != "comparison"
            or not secrets.compare_digest(req.claim_sha256, digest(claim.token.encode()))
        ):
            raise StoreError("claim_conflict")
        return task, req, _records(connection, task.task_id)[req.request_id]

    def save_slot(
        self,
        claim: RepairClaim,
        item: SlotResult,
        *,
        expected_revision: int,
        expected_sha256: str,
        fence: RepairFence,
    ) -> ComparisonMutation:
        item = _validated(SlotResult, item)
        with self._base._transaction(write=True) as connection:
            task, req, record = self._owned(connection, claim, fence)
            index = SLOTS.index(item.slot)
            if index < len(record.results):
                if _bytes(item) != _bytes(record.results[index]):
                    raise StoreError("slot_conflict")
                return _result(Mutation(task, digest(_bytes(task)), req), record)
            self._cas(task, expected_revision, expected_sha256)
            if (
                req.status != "pending"
                or record.status != "reserved"
                or index != len(record.results)
            ):
                raise StoreError("slot_conflict")
            if not _bound(record.plan, item, index):
                raise StoreError("attempt_binding")
            # An interrupted session never authorizes another slot in this request.
            if record.results and record.results[-1].report.status in (
                "cancelled",
                "outcome_unknown",
                "inconclusive",
            ):
                raise StoreError("comparison_stopped")
            record = _new(record, results=(*record.results, item))
            self._put_comparison(connection, record)
            changed = connection.execute(
                update(attempts)
                .where(
                    attempts.c.attempt_id == item.report.attempt_id,
                    attempts.c.comparison_id == record.plan.comparison_id,
                    attempts.c.slot_index == index,
                    attempts.c.status == "admitted",
                )
                .values(status="reported", report_sha256=digest(_bytes(item)))
            )
            if changed.rowcount != 1:
                raise StoreError("attempt_conflict")
            return _result(self._commit(connection, task, task, "comparison_slot"), record)

    def finalize_comparison(
        self,
        claim: RepairClaim,
        *,
        expected_revision: int,
        expected_sha256: str,
        fence: RepairFence,
        baseline: SnapshotHandle,
        candidate: SnapshotHandle,
        image_root: Path,
    ) -> ComparisonMutation:
        with self._base._transaction(write=True) as connection:
            task, req, record = self._owned(connection, claim, fence)
            self._cas(task, expected_revision, expected_sha256)
            if req.status != "pending" or record.status != "reserved":
                raise StoreError("claim_conflict")
            verified = verify_versions(record.plan, baseline, candidate, image_root)
            report = make_report(record.plan, record.results, versions_verified=verified)
            record = _new(record, status="finished", report=report, finished_at=self._now())
            self._put_comparison(connection, record)
            outcome = report.outcome
            req = _new(
                req,
                status=(
                    "completed"
                    if outcome in ("candidate_verified", "rejected")
                    else ("outcome_unknown" if outcome == "outcome_unknown" else "failed")
                ),
                error_code=None if outcome in ("candidate_verified", "rejected") else "TOOL_FAILED",
            )
            if outcome == "candidate_verified":
                new = self._finish_verified(task)
            elif outcome == "rejected":
                new = _new(task, phase="ready")
            else:
                new = _new(
                    task,
                    phase="finished",
                    outcome=outcome,
                    error_code="TOOL_FAILED",
                    finished_at=self._now(),
                )
            return _result(self._commit(connection, task, new, "settled", req), record)

    def _finish_verified(self, task: RepairTask) -> RepairTask:
        """Only finalize_comparison calls this after deriving the stored evidence verdict."""
        return _new(task, phase="finished", outcome="candidate_verified", finished_at=self._now())

    def reconcile_comparison(
        self, task_id: str, *, expected_revision: int, expected_sha256: str
    ) -> ComparisonMutation:
        with RepairFence(self.directory, _uuid(task_id)) as fence:
            return self.reconcile_comparison_held(
                task_id,
                expected_revision=expected_revision,
                expected_sha256=expected_sha256,
                fence=fence,
            )

    def reconcile_comparison_held(
        self, task_id: str, *, expected_revision: int, expected_sha256: str, fence: RepairFence
    ) -> ComparisonMutation:
        fence.require(self.directory, _uuid(task_id))
        with self._base._transaction(write=True) as connection:
            task, requests, _ = self._read(connection, task_id)
            self._cas(task, expected_revision, expected_sha256)
            req = next(
                (
                    r
                    for r in requests.values()
                    if r.operation == "comparison" and r.status == "pending"
                ),
                None,
            )
            if req is None:
                raise StoreError("comparison_not_pending")
            record = _records(connection, task_id)[req.request_id]
            record = _new(record, status="outcome_unknown", finished_at=self._now())
            self._put_comparison(connection, record)
            connection.execute(
                update(attempts)
                .where(
                    attempts.c.comparison_id == record.plan.comparison_id,
                    attempts.c.status == "admitted",
                )
                .values(status="unknown")
            )
            req = _new(req, status="outcome_unknown", error_code="INTERRUPTED")
            new = _new(
                task,
                phase="finished",
                outcome="outcome_unknown",
                error_code="INTERRUPTED",
                finished_at=self._now(),
            )
            return _result(self._commit(connection, task, new, "reconciled", req), record)
