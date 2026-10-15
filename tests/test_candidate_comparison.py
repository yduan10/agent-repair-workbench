"""P0-06 T07 verdict rules, deterministic reports are not real model evidence."""

import asyncio
import importlib
import json
import os
import tempfile
from pathlib import Path
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
from agent_workbench.candidate_execution.docker import verified_image
from agent_workbench.candidate_execution.models import STEPS, OracleReport, OracleStep
from agent_workbench.candidate_execution.oracle import ORACLE_SHA256, SUITE_SHA256
from agent_workbench.candidates.contracts import CandidatePatch, SnapshotRef
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.mcp_config import ROOT, canonical, digest
from agent_workbench.repair_cases.profiles import get_profile

H = "a" * 64
IMAGE_ID = "sha256:" + "b" * 64


def plan() -> ComparisonPlan:
    profile = get_profile("output_mismatch")
    tree = digest(canonical({"server.py": profile.source_sha256}))
    baseline = SnapshotRef(
        snapshot_id=str(uuid4()),
        kind="baseline",
        manifest_sha256=profile.manifest_sha256,
        file_sha256=profile.source_sha256,
        tree_sha256=tree,
    )
    candidate = SnapshotRef(
        snapshot_id=str(uuid4()),
        kind="candidate",
        manifest_sha256=profile.manifest_sha256,
        file_sha256="c" * 64,
        tree_sha256="d" * 64,
        baseline_id=baseline.snapshot_id,
        baseline_tree_sha256=tree,
        patch_sha256=H,
    )
    return ComparisonPlan(
        task_id=str(uuid4()),
        request_id=str(uuid4()),
        comparison_id=str(uuid4()),
        baseline=baseline,
        candidate=candidate,
        attempts=tuple(str(uuid4()) for _ in range(4)),
        suite_sha256=H,
        oracle_sha256=H,
        image_id=IMAGE_ID,
        image_source_sha256=H,
    )


def reports(p: ComparisonPlan) -> tuple[SlotResult, ...]:
    results = []
    for index, slot in enumerate(SLOTS):
        snapshot = p.baseline if index < 2 else p.candidate
        steps = [OracleStep(name=name, status="passed", code="ok") for name in STEPS]
        if index == 0:
            for step in steps:
                if step.name in ("valid_one", "valid_zero", "valid_negative"):
                    step.status, step.code = "failed", "count_type"
        report = OracleReport(
            attempt_id=p.attempts[index],
            snapshot_id=snapshot.snapshot_id,
            snapshot_tree_sha256=snapshot.tree_sha256,
            snapshot_file_sha256=snapshot.file_sha256,
            suite_sha256=p.suite_sha256,
            oracle_sha256=p.oracle_sha256,
            image_id=p.image_id,
            image_source_sha256=p.image_source_sha256,
            scenario="wrong_type" if index % 2 == 0 else "pass",
            steps=steps,
            status="failed" if index == 0 else "passed",
            cleanup="removed",
            snapshot_verified_before=True,
            snapshot_verified_after=True,
        )
        results.append(SlotResult(slot=slot, report=report))
    return tuple(results)


def test_original_failed_candidate_passes_all_is_verified_not_accepted() -> None:
    p = plan()
    result = make_report(p, reports(p), versions_verified=True)
    assert result.outcome == "candidate_verified"
    assert not result.accepted
    assert ComparisonReport.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("slot", [2, 3])
def test_any_candidate_failure_rejects_even_if_original_fixed(slot: int) -> None:
    p = plan()
    items = reports(p)
    items[slot].report.status = "failed"
    items[slot].report.steps[4].status = "failed"
    items[slot].report.steps[4].code = "count_value"
    assert make_report(p, items, versions_verified=True).outcome == "rejected"


def test_baseline_must_match_expected_failure_and_normal_control() -> None:
    p = plan()
    items = reports(p)
    items[0].report.steps[2].code = "count_value"
    assert make_report(p, items, versions_verified=True).reason == "baseline_not_reproduced"
    items = reports(p)
    items[1].report.status = "failed"
    items[1].report.steps[2].status = "failed"
    items[1].report.steps[2].code = "count_value"
    assert make_report(p, items, versions_verified=True).reason == "baseline_not_reproduced"


@pytest.mark.parametrize(
    "field",
    [
        "attempt_id",
        "snapshot_id",
        "snapshot_tree_sha256",
        "snapshot_file_sha256",
        "suite_sha256",
        "oracle_sha256",
        "image_id",
        "image_source_sha256",
        "scenario",
    ],
)
def test_stale_or_foreign_execution_cannot_verify(field: str) -> None:
    p = plan()
    items = reports(p)
    value = (
        str(uuid4())
        if field in ("attempt_id", "snapshot_id")
        else "sha256:" + "e" * 64
        if field == "image_id"
        else "wrong_type"
        if field == "scenario"
        else "e" * 64
    )
    setattr(items[3].report, field, value)
    assert make_report(p, items, versions_verified=True).reason == "version_mismatch"


@pytest.mark.parametrize("count", range(4))
def test_missing_runs_are_incomplete_not_padded(count: int) -> None:
    p = plan()
    assert make_report(p, reports(p)[:count], versions_verified=True).outcome == "inconclusive"


def test_tampering_does_not_keep_old_verified_label() -> None:
    p = plan()
    assert make_report(p, reports(p), versions_verified=False).reason == "version_mismatch"
    result = make_report(p, reports(p), versions_verified=True).model_dump(mode="json")
    result["versions_verified"] = False
    with pytest.raises(ValidationError):
        ComparisonReport.model_validate(result)


@pytest.mark.parametrize(
    "state,cleanup,expected",
    [
        ("cancelled", "removed", "cancelled"),
        ("outcome_unknown", "unconfirmed", "outcome_unknown"),
        ("inconclusive", "removed", "inconclusive"),
    ],
)
def test_interruption_is_not_failure_or_verified(state: str, cleanup: str, expected: str) -> None:
    p = plan()
    items = reports(p)
    items[2].report.status = state  # type: ignore[assignment]
    items[2].report.cleanup = cleanup  # type: ignore[assignment]
    assert make_report(p, items[:3], versions_verified=True).outcome == expected


def test_duplicate_and_reordered_slots_rejected() -> None:
    p = plan()
    items = reports(p)
    for malformed in [(items[0], items[0]), (items[1], items[0]), items[::-1]]:
        with pytest.raises(ValidationError):
            make_report(p, malformed, versions_verified=True)
    raw = p.model_dump(mode="json")
    raw["attempts"] = [p.attempts[0]] * 4
    with pytest.raises(ValidationError):
        ComparisonPlan.model_validate_json(json.dumps(raw))


def test_model_cannot_forge_verified_or_accepted() -> None:
    p = plan()
    bad = make_report(p, (), versions_verified=True).model_dump(mode="json")
    bad["outcome"], bad["reason"] = "candidate_verified", "frozen_suite_passed"
    with pytest.raises(ValidationError):
        ComparisonReport.model_validate_json(json.dumps(bad))
    good = make_report(p, reports(p), versions_verified=True).model_dump(mode="json")
    good["accepted"] = True
    with pytest.raises(ValidationError):
        ComparisonReport.model_validate_json(json.dumps(good))


def test_skipped_required_step_and_faked_passed_rejected() -> None:
    p = plan()
    items = reports(p)
    items[2].report.steps[-1].status, items[2].report.steps[-1].code = "not_run", "not_run"
    with pytest.raises(ValidationError):
        make_report(p, items, versions_verified=True)
    items[2].report.status = "inconclusive"
    assert make_report(p, items, versions_verified=True).outcome == "inconclusive"


@pytest.mark.parametrize("remaining", [0, 15, float("nan"), float("inf")])
def test_expired_or_invalid_task_budget_never_starts(monkeypatch, remaining: float) -> None:
    module = importlib.import_module("agent_workbench.candidate_execution.compare")
    monkeypatch.setattr(module, "verify_versions", lambda *args: True)

    async def forbidden(*args, **kwargs):
        pytest.fail("external execution started without sufficient task allowance")

    monkeypatch.setattr(module, "run_oracle", forbidden)
    result = asyncio.run(
        compare(
            plan(),
            None,
            None,
            image_root=ROOT,
            save_result=forbidden,
            remaining_seconds=lambda: remaining,
        )
    )
    assert result.outcome == "inconclusive"
    assert result.results == ()


def test_persistence_failure_stops_before_any_next_container(monkeypatch) -> None:
    module = importlib.import_module("agent_workbench.candidate_execution.compare")
    p = plan()
    items = reports(p)
    calls = []
    monkeypatch.setattr(module, "verify_versions", lambda *args: True)

    async def run(*args, **kwargs):
        calls.append(kwargs["attempt_id"])
        return items[len(calls) - 1].report

    async def save(item):
        raise OSError("injected_disk_failure")

    monkeypatch.setattr(module, "run_oracle", run)
    with pytest.raises(OSError, match="injected_disk_failure"):
        asyncio.run(
            compare(
                p,
                None,
                None,
                image_root=ROOT,
                save_result=save,
                remaining_seconds=lambda: 600,
            )
        )
    assert calls == [p.attempts[0]]


def test_versions_changed_after_runs_invalidates_verdict(monkeypatch) -> None:
    module = importlib.import_module("agent_workbench.candidate_execution.compare")
    p = plan()
    items = reports(p)
    checks = iter([True, False])
    monkeypatch.setattr(module, "verify_versions", lambda *args: next(checks))

    async def run(*args, **kwargs):
        return items[p.attempts.index(kwargs["attempt_id"])].report

    async def save(item):
        pass

    monkeypatch.setattr(module, "run_oracle", run)
    result = asyncio.run(
        compare(
            p,
            None,
            None,
            image_root=ROOT,
            save_result=save,
            remaining_seconds=lambda: 600,
        )
    )
    assert len(result.results) == 4
    assert result.outcome == "inconclusive"
    assert result.reason == "version_mismatch"


@pytest.mark.docker
@pytest.mark.skipif(os.getenv("AWB_CANDIDATE_DOCKER_TEST") != "1", reason="explicit Docker gate")
@pytest.mark.parametrize(
    "body,outcome",
    [
        ('return {"count": count}', "candidate_verified"),
        ('return {"count": 1}', "rejected"),
        ('return {"count": count if scenario == "wrong_type" else 0}', "rejected"),
    ],
)
def test_real_four_container_comparison(body: str, outcome: str) -> None:
    # Temporary reviewed snapshots only, never product history or private model data.
    with tempfile.TemporaryDirectory(dir=ROOT / "artifacts", prefix="p006-compare-") as tmp:
        snapshots = SnapshotStore(Path(tmp) / "snapshots")
        base = snapshots.create_baseline(str(uuid4()))
        patch = CandidatePatch(
            expected_baseline_hash=base.ref.tree_sha256,
            expected_file_hash=base.ref.file_sha256,
            replacement="def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
            f"    {body}\n",
        )
        candidate = snapshots.create_candidate(base, str(uuid4()), patch)
        image = verified_image(ROOT)
        p = ComparisonPlan(
            task_id=str(uuid4()),
            request_id=str(uuid4()),
            comparison_id=str(uuid4()),
            baseline=base.ref,
            candidate=candidate.ref,
            attempts=tuple(str(uuid4()) for _ in range(4)),
            suite_sha256=SUITE_SHA256,
            oracle_sha256=ORACLE_SHA256,
            image_id=image.image_id,
            image_source_sha256=image.source_sha256,
        )
        observed = []

        async def save(item: SlotResult) -> None:
            observed.append(item)

        result = asyncio.run(
            compare(
                p,
                base,
                candidate,
                image_root=ROOT,
                save_result=save,
                remaining_seconds=lambda: 600,
            )
        )
        assert len(observed) == 4
        assert result.outcome == outcome
        assert all(item.report.cleanup == "removed" for item in observed)
        assert result.results[0].report.status == "failed"
        assert result.results[1].report.status == "passed"
        assert result.accepted is False
