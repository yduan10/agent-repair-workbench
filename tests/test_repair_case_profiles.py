"""H1/H2 fixed profiles, deterministic exact bindings; no model or Docker calls."""

import json
from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution.compare import make_report
from agent_workbench.candidate_execution.oracle import ORACLE_SAFETY_FILES, SEQUENCE, SUITE_SHA256
from agent_workbench.candidates.contracts import CandidateError, CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.controlled_tools.resources import load_case, load_repair_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.mcp_config import ROOT, canonical, digest
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_cases.bindings import validate_baseline_binding
from agent_workbench.repair_cases.profiles import get_profile, profile_for_manifest
from agent_workbench.repair_store.reproduction_models import result_outcome
from tests.test_candidate_comparison import plan, reports

CASES = ("output_mismatch", "counter_offset")
FAILURES = {"valid_one", "valid_zero", "valid_negative"}


def case_plan(case_id):
    original = plan()
    profile = get_profile(case_id)
    tree = digest(canonical({"server.py": profile.source_sha256}))
    original = original.model_copy(
        update={
            "baseline": original.baseline.model_copy(
                update={
                    "manifest_sha256": profile.manifest_sha256,
                    "file_sha256": profile.source_sha256,
                    "tree_sha256": tree,
                }
            ),
            "candidate": original.candidate.model_copy(
                update={"manifest_sha256": profile.manifest_sha256, "baseline_tree_sha256": tree}
            ),
        }
    )
    items = reports(original)
    for step in items[0].report.steps:
        if step.name in FAILURES:
            step.code = profile.failure_code
    return original, items


@pytest.mark.parametrize("case_id", CASES)
def test_registered_resources_and_snapshots_bind_exactly(case_id, tmp_path):
    profile = get_profile(case_id)
    registry = load_repair_case(
        case_id, task_id=str(uuid4()), budget=Budget(total_tokens=10000, output_tokens=1000)
    )
    assert registry.manifest_sha256 == profile.manifest_sha256
    assert registry.source_sha256() == profile.source_sha256
    assert digest(registry.verify_case()) == profile.envelope_sha256
    assert profile_for_manifest(profile.manifest_sha256) == profile
    snapshots = SnapshotStore(tmp_path / "snapshots")
    base = snapshots.create_baseline(str(uuid4()), case_id=case_id)
    assert validate_baseline_binding(base.ref) == profile
    snapshots.verify(base)
    patch = CandidatePatch(
        expected_baseline_hash=base.ref.tree_sha256,
        expected_file_hash=base.ref.file_sha256,
        replacement="def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
        '    return {"count": count}\n',
    )
    candidate = snapshots.create_candidate(base, str(uuid4()), patch)
    snapshots.verify(candidate)
    assert candidate.ref.manifest_sha256 == profile.manifest_sha256
    assert candidate.ref.baseline_tree_sha256 == base.ref.tree_sha256
    assert snapshots.diff(base, candidate).candidate == candidate.ref


def test_old_loader_and_default_snapshot_remain_compatible(tmp_path):
    old = load_case(
        "output_mismatch",
        task_id=str(uuid4()),
        intent="propose_repair",
        budget=Budget(total_tokens=10000, output_tokens=1000),
    )
    current = load_repair_case(
        "output_mismatch",
        task_id=str(uuid4()),
        budget=Budget(total_tokens=10000, output_tokens=1000),
    )
    assert old.verify_case() == current.verify_case()
    base = SnapshotStore(tmp_path / "snapshots").create_baseline(str(uuid4()))
    profile = get_profile("output_mismatch")
    assert (base.ref.manifest_sha256, base.ref.file_sha256) == (
        profile.manifest_sha256,
        profile.source_sha256,
    )
    assert load_case(
        "passing",
        task_id=str(uuid4()),
        intent="check_only",
        budget=Budget(total_tokens=10000, output_tokens=1000),
    )


def test_new_case_initial_schema_is_pass_not_synthetic_type_failure():
    registry = load_repair_case(
        "counter_offset",
        task_id=str(uuid4()),
        budget=Budget(total_tokens=10000, output_tokens=1000),
    )
    envelope = json.loads(registry.verify_case())
    assert type(envelope["result"]["structured_content"]["count"]) is int
    assert envelope["result"]["structured_content"]["count"] == 0
    assert registry.initial_report().status == "passed"
    # Host policy and hidden expected sequence are not seeded into the model's evidence.
    seed = registry._records[next(iter(registry._records))].raw.decode()
    assert "count_value" not in seed and "valid_zero" not in seed and "expected_count" not in seed


def test_only_authorized_function_changes_between_fixed_sources():
    old, new = [
        (ROOT / get_profile(case).resource_directory / "source/server.py")
        .read_bytes()
        .splitlines(True)
        for case in CASES
    ]
    assert old[:106] == new[:106] and old[110:] == new[110:]
    assert old[106:110] != new[106:110]


@pytest.mark.parametrize("case_id", ["passing", "../counter_offset", "/tmp/case", "unknown"])
def test_no_unregistered_repair_case_or_path(case_id, tmp_path):
    with pytest.raises(ResourceError, match="INVALID_INPUT"):
        load_repair_case(
            case_id, task_id=str(uuid4()), budget=Budget(total_tokens=10000, output_tokens=1000)
        )
    with pytest.raises(CandidateError, match="SOURCE_MANIFEST_MISMATCH"):
        SnapshotStore(tmp_path / "snapshots").create_baseline(str(uuid4()), case_id=case_id)


def test_old_analysis_loader_does_not_expand_to_repair_case():
    with pytest.raises(ResourceError, match="INVALID_INPUT"):
        load_case(
            "counter_offset",
            task_id=str(uuid4()),
            intent="propose_repair",
            budget=Budget(total_tokens=10000, output_tokens=1000),
        )
    with pytest.raises(TypeError):
        load_repair_case(
            "counter_offset",
            task_id=str(uuid4()),
            budget=Budget(total_tokens=10000, output_tokens=1000),
            root=ROOT,
        )


def test_profiles_immutable_unique_and_hash_bound():
    profiles = [get_profile(case) for case in CASES]
    assert len({p.profile_digest for p in profiles}) == 2
    with pytest.raises(FrozenInstanceError):
        profiles[0].failure_code = "count_value"
    with pytest.raises(ValueError):
        profile_for_manifest("a" * 64)
    assert all(
        "src/agent_workbench/repair_cases/" + name in ORACLE_SAFETY_FILES
        for name in ("__init__.py", "profiles.py", "bindings.py")
    )
    # Existing host oracle sequence and suite are unchanged by adding a baseline profile.
    assert SEQUENCE == (
        ("valid_one", 1, 1),
        ("invalid_type", "bad", None),
        ("valid_zero", 0, 2),
        ("valid_negative", -1, 3),
    )
    assert SUITE_SHA256 == "6f82989f12467fe0c0e5f227be5f71d010d5723859deb609e0d7552644a9b10e"


@pytest.mark.parametrize("case_id", CASES)
def test_t05_and_t07_accept_only_exact_profile_failure(case_id):
    p, items = case_plan(case_id)
    assert result_outcome(items[0].report, True, baseline=p.baseline) == "observed_failure"
    assert make_report(p, items, versions_verified=True).outcome == "candidate_verified"
    other = "count_value" if case_id == "output_mismatch" else "count_type"
    for step in items[0].report.steps:
        if step.name in FAILURES:
            step.code = other
    assert result_outcome(items[0].report, True, baseline=p.baseline) == "inconclusive"
    assert make_report(p, items, versions_verified=True).outcome == "inconclusive"


@pytest.mark.parametrize("case_id", CASES)
@pytest.mark.parametrize("mutation", ["mixed", "extra", "missing", "manifest", "file", "tree"])
def test_mixed_or_cross_bound_reports_cannot_authorize_repair(case_id, mutation):
    p, items = case_plan(case_id)
    report = items[0].report
    if mutation == "mixed":
        next(s for s in report.steps if s.name == "valid_one").code = (
            "count_value" if case_id == "output_mismatch" else "count_type"
        )
    elif mutation == "extra":
        report.steps[0].status, report.steps[0].code = "failed", "protocol_mismatch"
    elif mutation == "missing":
        step = next(s for s in report.steps if s.name == "valid_zero")
        step.status, step.code = "passed", "ok"
    else:
        p = p.model_copy(
            update={"baseline": p.baseline.model_copy(update={mutation + "_sha256": "a" * 64})}
        )
    assert result_outcome(report, True, baseline=p.baseline) == "inconclusive"
    # malformed OracleReport is rejected at DTO boundary; otherwise no success verdict.
    try:
        result = make_report(p, items, versions_verified=True)
    except ValueError:
        return
    assert result.outcome != "candidate_verified"


@pytest.mark.parametrize("case_id", CASES)
def test_cross_profile_snapshot_and_diff_rejected(case_id, tmp_path):
    snapshots = SnapshotStore(tmp_path / "snapshots")
    base = snapshots.create_baseline(str(uuid4()), case_id=case_id)
    other = get_profile("counter_offset" if case_id == "output_mismatch" else "output_mismatch")
    forged = replace(
        base, ref=base.ref.model_copy(update={"manifest_sha256": other.manifest_sha256})
    )
    with pytest.raises(CandidateError):
        snapshots.verify(forged)
    with pytest.raises(CandidateError):
        validate_baseline_binding(forged.ref)
