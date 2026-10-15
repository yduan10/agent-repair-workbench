"""Filesystem capabilities are rebuilt only from audited records under one fixed root."""

from pathlib import Path
from typing import Literal

from agent_workbench.candidate_execution.compare import verify_versions
from agent_workbench.candidates.contracts import CandidateError, SnapshotRef
from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore
from agent_workbench.repair_cases.bindings import validate_baseline_binding
from agent_workbench.repair_store.comparison_models import ComparisonRecord
from agent_workbench.repair_store.models import CandidateRecord, Mutation, RepairTask
from agent_workbench.repair_store.reproductions import ReproductionStore
from agent_workbench.run_store.models import StoreError

from .models import (
    CandidateDiff,
    CandidateView,
    ComparisonView,
    RepairDetail,
    RepairList,
    SlotView,
    TaskView,
)


def task_view(value: Mutation) -> TaskView:
    task = value.task
    return TaskView(
        task_id=task.task_id,
        case_id=validate_baseline_binding(task.baseline).case_id,
        source_analysis_id=task.source_analysis_id,
        mode=task.mode,
        phase=task.phase,
        recorded_outcome=task.outcome,
        error_code=task.error_code,
        revision=task.revision,
        sha256=value.task_sha256,
        started_at=task.started_at,
        finished_at=task.finished_at,
        budget=task.budget,
        usage=task.usage,
        candidate_count=task.candidate_count,
    )


class RepairReader:
    def __init__(self, directory: Path, image_root: Path):
        self.store = ReproductionStore(directory)
        self.snapshots = SnapshotStore(directory / "repair-snapshots")
        self.image_root = image_root

    def close(self) -> None:
        self.store.close()

    def _handle(self, ref: SnapshotRef) -> SnapshotHandle:
        # A host path is never read from HTTP, serialized metadata, or a model.
        ref = SnapshotRef.model_validate_json(ref.model_dump_json())
        return SnapshotHandle(ref, self.snapshots.root / ref.snapshot_id)

    def list(self, limit: int) -> RepairList:
        return RepairList(repairs=tuple(task_view(item) for item in self.store.list_tasks(limit)))

    def _candidate(self, task: RepairTask, item: CandidateRecord) -> CandidateView:
        status: Literal["verified", "unavailable", "not_created"] = "not_created"
        if item.snapshot is not None:
            try:
                self.snapshots.verify(self._handle(task.baseline))
                self.snapshots.verify(self._handle(item.snapshot))
                status = "verified"
            except (CandidateError, OSError, ValueError):
                status = "unavailable"
        return CandidateView(
            candidate_id=item.candidate_id,
            sequence=item.sequence,
            status=item.status,
            snapshot_status=status,
            snapshot_sha256=item.snapshot.tree_sha256 if item.snapshot else None,
            error_code=item.error_code,
            created_at=item.created_at,
            finished_at=item.finished_at,
        )

    def _comparison(self, item: ComparisonRecord) -> ComparisonView:
        plan = item.plan
        current = verify_versions(
            plan, self._handle(plan.baseline), self._handle(plan.candidate), self.image_root
        )
        return ComparisonView(
            task_id=plan.task_id,
            comparison_id=plan.comparison_id,
            candidate_id=plan.candidate.snapshot_id,
            status=item.status,
            verification="unavailable"
            if not current
            else "verified"
            if item.report
            else "not_finished",
            recorded_outcome=item.report.outcome if item.report else None,
            current_outcome=item.report.outcome if current and item.report else None,
            reason=item.report.reason if current and item.report else None,
            unavailable_reason=None if current else "artifact_or_version_mismatch",
            suite_sha256=plan.suite_sha256,
            oracle_sha256=plan.oracle_sha256,
            created_at=item.created_at,
            finished_at=item.finished_at,
            slots=tuple(
                SlotView(
                    slot=result.slot,
                    status=result.report.status,
                    cleanup=result.report.cleanup,
                    steps=tuple(result.report.steps),
                )
                for result in item.results
            )
            if current
            else (),
        )

    def detail(self, task_id: str) -> RepairDetail:
        task, candidates, comparisons = self.store.read_detail(task_id)
        return RepairDetail(
            task=task_view(task),
            candidates=tuple(self._candidate(task.task, item) for item in candidates),
            comparisons=tuple(self._comparison(item) for item in comparisons),
        )

    def diff(self, task_id: str, candidate_id: str) -> CandidateDiff:
        task, candidates, _ = self.store.read_detail(task_id)
        item = next((c for c in candidates if c.candidate_id == candidate_id), None)
        if item is None:
            raise StoreError("candidate_not_found")
        if item.snapshot is None:
            raise CandidateError("SNAPSHOT_UNAVAILABLE")
        value = self.snapshots.diff(self._handle(task.task.baseline), self._handle(item.snapshot))
        return CandidateDiff(task_id=task_id, candidate_id=candidate_id, diff=value)

    def comparison(self, task_id: str, comparison_id: str) -> ComparisonView:
        _, _, comparisons = self.store.read_detail(task_id)
        item = next((c for c in comparisons if c.plan.comparison_id == comparison_id), None)
        if item is None:
            raise StoreError("comparison_not_found")
        return self._comparison(item)
