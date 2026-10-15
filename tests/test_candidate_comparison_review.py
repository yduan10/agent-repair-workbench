"""Independent comparison boundary probes; synthetic DTOs, no product runs."""

import asyncio
import importlib
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent_workbench.candidate_execution.compare import (
    SLOTS,
    ComparisonPlan,
    ComparisonReport,
    SlotResult,
    compare,
    make_report,
)
from agent_workbench.candidate_execution.models import STEPS, OracleReport, OracleStep
from agent_workbench.candidates.contracts import SnapshotRef
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.repair_cases.profiles import get_profile


def fixture():
    h = "a" * 64
    profile = get_profile("output_mismatch")
    tree = digest(canonical({"server.py": profile.source_sha256}))
    base = SnapshotRef(
        snapshot_id=str(uuid4()),
        kind="baseline",
        manifest_sha256=profile.manifest_sha256,
        file_sha256=profile.source_sha256,
        tree_sha256=tree,
    )
    changed = SnapshotRef(
        snapshot_id=str(uuid4()),
        kind="candidate",
        manifest_sha256=profile.manifest_sha256,
        file_sha256="b" * 64,
        tree_sha256="c" * 64,
        baseline_id=base.snapshot_id,
        baseline_tree_sha256=tree,
        patch_sha256=h,
    )
    plan = ComparisonPlan(
        task_id=str(uuid4()),
        request_id=str(uuid4()),
        comparison_id=str(uuid4()),
        baseline=base,
        candidate=changed,
        attempts=tuple(str(uuid4()) for _ in range(4)),
        suite_sha256=h,
        oracle_sha256=h,
        image_id="sha256:" + h,
        image_source_sha256=h,
    )
    items = []
    for index, slot in enumerate(SLOTS):
        snapshot = base if index < 2 else changed
        steps = [OracleStep(name=n, status="passed", code="ok") for n in STEPS]
        if index == 0:
            for step in steps:
                if step.name in ("valid_one", "valid_zero", "valid_negative"):
                    step.status, step.code = "failed", "count_type"
        report = OracleReport(
            attempt_id=plan.attempts[index],
            snapshot_id=snapshot.snapshot_id,
            snapshot_tree_sha256=snapshot.tree_sha256,
            snapshot_file_sha256=snapshot.file_sha256,
            suite_sha256=h,
            oracle_sha256=h,
            image_id=plan.image_id,
            image_source_sha256=h,
            scenario="wrong_type" if index % 2 == 0 else "pass",
            steps=steps,
            status="failed" if index == 0 else "passed",
            cleanup="removed",
            snapshot_verified_before=True,
            snapshot_verified_after=True,
        )
        items.append(SlotResult(slot=slot, report=report))
    return plan, tuple(items)


def test_python_dto_cannot_preserve_verified_with_mutated_failed_step():
    plan, items = fixture()
    items[2].report.steps[2].status, items[2].report.steps[2].code = "failed", "count_value"
    with pytest.raises(ValidationError):
        ComparisonReport(
            plan=plan,
            results=items,
            versions_verified=True,
            outcome="candidate_verified",
            reason="frozen_suite_passed",
        )


@pytest.mark.parametrize("terminal", ["cancelled", "inconclusive", "outcome_unknown"])
def test_terminal_result_saved_once_and_no_next_attempt(monkeypatch, terminal):
    module = importlib.import_module("agent_workbench.candidate_execution.compare")
    plan, items = fixture()
    items[0].report.status = terminal
    items[0].report.error = "run_cancelled" if terminal == "cancelled" else "protocol_error"
    calls, saved = [], []
    monkeypatch.setattr(module, "verify_versions", lambda *args: True)

    async def run(*args, **kwargs):
        calls.append(kwargs["attempt_id"])
        return items[0].report

    async def save(item):
        saved.append(item.report.attempt_id)

    monkeypatch.setattr(module, "run_oracle", run)
    output = asyncio.run(
        compare(plan, None, None, image_root=None, save_result=save, remaining_seconds=lambda: 600)
    )
    assert calls == saved == [plan.attempts[0]]
    assert output.outcome == terminal


def test_empty_completion_is_never_verified():
    plan, _ = fixture()
    output = make_report(plan, (), versions_verified=True)
    assert output.outcome == "inconclusive" and output.results == ()
