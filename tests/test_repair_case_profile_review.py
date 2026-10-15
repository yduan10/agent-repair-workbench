"""Independent profile isolation probes; real temp snapshots/ledger, synthetic reports."""

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution import oracle
from agent_workbench.candidate_execution.compare import ComparisonPlan, make_report
from agent_workbench.candidates.contracts import CandidateError, CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.controlled_tools.resources import load_repair_case
from agent_workbench.repair_cases.profiles import get_profile
from agent_workbench.repair_runtime.tools import RepairToolBridge
from agent_workbench.repair_store.reproduction_models import result_outcome
from agent_workbench.repair_store.reproductions import ReproductionStore
from tests.test_repair_case_ledger import profile_context as profile_context
from tests.test_repair_case_profiles import CASES, case_plan


def test_identical_corrected_bytes_do_not_collapse_case_provenance(tmp_path):
    snapshots = SnapshotStore(tmp_path / "snapshots")
    pairs = []
    for case_id in CASES:
        base = snapshots.create_baseline(str(uuid4()), case_id=case_id)
        patch = CandidatePatch(
            expected_baseline_hash=base.ref.tree_sha256,
            expected_file_hash=base.ref.file_sha256,
            replacement=(
                "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
                '    return {"count": count}\n'
            ),
        )
        candidate = snapshots.create_candidate(base, str(uuid4()), patch)
        pairs.append((base, candidate))
    (first_base, first_candidate), (second_base, second_candidate) = pairs
    assert first_candidate.ref.file_sha256 == second_candidate.ref.file_sha256
    assert first_candidate.ref.manifest_sha256 != second_candidate.ref.manifest_sha256
    with pytest.raises(CandidateError):
        snapshots.diff(first_base, second_candidate)
    with pytest.raises(CandidateError):
        snapshots.diff(second_base, first_candidate)
    plan, _ = case_plan(CASES[0])
    with pytest.raises(ValueError):
        ComparisonPlan.model_validate(
            {**plan.model_dump(), "baseline": first_base.ref, "candidate": second_candidate.ref}
        )
    forged = replace(
        first_candidate,
        ref=first_candidate.ref.model_copy(
            update={
                "manifest_sha256": second_base.ref.manifest_sha256,
            }
        ),
    )
    with pytest.raises(CandidateError):
        snapshots.verify(forged)


@pytest.mark.parametrize("case_id", CASES)
def test_mutated_empty_steps_or_wrong_snapshot_do_not_count_as_reproduced(case_id):
    plan, items = case_plan(case_id)
    report = items[0].report
    report.snapshot_id = str(uuid4())
    assert result_outcome(report, True, baseline=plan.baseline) == "inconclusive"
    report.snapshot_id = plan.baseline.snapshot_id
    report.steps.clear()
    assert result_outcome(report, True, baseline=plan.baseline) == "inconclusive"
    with pytest.raises(ValueError):
        make_report(plan, items, versions_verified=True)


def test_mutation_of_new_profile_module_invalidates_oracle_closure(monkeypatch):
    original = Path.read_bytes
    target = (
        Path(oracle.__file__).resolve().parents[3] / "src/agent_workbench/repair_cases/profiles.py"
    )
    before = oracle.oracle_sha256()

    def changed(path):
        data = original(path)
        return data + b"\n" if path == target else data

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert oracle.oracle_sha256() != before
    assert oracle.verify_oracle() is False
    assert oracle.suite_sha256() == oracle.SUITE_SHA256


def test_registry_swapped_after_bridge_creation_is_rejected_before_admission(profile_context):
    case_id, context = profile_context
    original, fence, saved, _, baseline, _, image_root = context
    registry = load_repair_case(case_id, task_id=saved.task.task_id, budget=saved.task.budget)
    store = ReproductionStore(original.directory)
    try:
        bridge = RepairToolBridge(
            store=store,
            registry=registry,
            baseline=baseline,
            snapshots=SnapshotStore(baseline.root.parent),
            image_root=image_root,
            fence=fence,
            remaining_seconds=lambda: 600,
        )
        request = next(x for x in registry.templates("diagnosis") if x.tool == "read_source")
        other = get_profile("counter_offset" if case_id == "output_mismatch" else "output_mismatch")
        registry.case_name = other.case_id
        registry.manifest_sha256 = other.manifest_sha256
        result = asyncio.run(bridge.execute("diagnosis", request, cursor=saved))
        assert result.response.error_code == "PERMISSION_DENIED"
        assert result.cursor.task == saved.task and result.cursor.task_sha256 == saved.task_sha256
        assert store.get(saved.task.task_id).task == saved.task
        assert not result.response.payload and not result.response.evidence_refs
    finally:
        store.close()
