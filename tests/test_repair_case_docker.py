"""H1/H2 explicit real Docker gate; hand-authored patches, no LLM or model success claim."""

import asyncio
import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution.compare import ComparisonPlan, SlotResult, compare
from agent_workbench.candidate_execution.docker import verified_image
from agent_workbench.candidate_execution.oracle import ORACLE_SHA256, SUITE_SHA256, run_oracle
from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.mcp_config import ROOT
from agent_workbench.repair_cases.profiles import get_profile
from agent_workbench.repair_store.reproduction_models import result_outcome

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(os.getenv("AWB_HELDOUT_DOCKER") != "1", reason="explicit real Docker gate"),
]


@pytest.mark.parametrize("case_id", ["output_mismatch", "counter_offset"])
def test_real_baseline_t05_profile_fingerprint(case_id):
    with tempfile.TemporaryDirectory(dir=ROOT / "artifacts", prefix="heldout-t05-") as temp:
        baseline = SnapshotStore(Path(temp) / "snapshots").create_baseline(
            str(uuid4()), case_id=case_id
        )
        report = asyncio.run(
            run_oracle(
                baseline,
                scenario="wrong_type",
                attempt_id=str(uuid4()),
                image_root=ROOT,
                stage_timeout=3,
                total_timeout=25,
            )
        )
        assert result_outcome(report, True, baseline=baseline.ref) == "observed_failure"
        assert report.cleanup == "removed"
        expected = get_profile(case_id).failure_code
        assert [s.code for s in report.steps if s.status == "failed"] == [expected] * 3


@pytest.mark.parametrize("case_id", ["output_mismatch", "counter_offset"])
@pytest.mark.parametrize(
    "body,outcome",
    [
        ('return {"count": count}', "candidate_verified"),
        ('return {"count": 1}', "rejected"),
        ('return {"count": int(count - 1) if scenario == "wrong_type" else count}', "rejected"),
        ('return {"count": count if scenario == "wrong_type" else 0}', "rejected"),
    ],
)
def test_real_t07_profile_candidate_and_regression(case_id, body, outcome):
    with tempfile.TemporaryDirectory(dir=ROOT / "artifacts", prefix="heldout-t07-") as temp:
        snapshots = SnapshotStore(Path(temp) / "snapshots")
        base = snapshots.create_baseline(str(uuid4()), case_id=case_id)
        candidate = snapshots.create_candidate(
            base,
            str(uuid4()),
            CandidatePatch(
                expected_baseline_hash=base.ref.tree_sha256,
                expected_file_hash=base.ref.file_sha256,
                replacement="def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
                f"    {body}\n",
            ),
        )
        image = verified_image(ROOT)
        plan = ComparisonPlan(
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

        async def save(result: SlotResult):
            observed.append(result)

        result = asyncio.run(
            compare(
                plan,
                base,
                candidate,
                image_root=ROOT,
                save_result=save,
                remaining_seconds=lambda: 600,
            )
        )
        assert len(observed) == 4
        assert result.outcome == outcome and result.accepted is False
        assert all(slot.report.cleanup == "removed" for slot in observed)
        assert observed[1].report.status == "passed"
        failures = [s.code for s in observed[0].report.steps if s.status == "failed"]
        assert failures == [get_profile(case_id).failure_code] * 3
