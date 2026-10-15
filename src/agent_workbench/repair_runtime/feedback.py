"""Only aggregate frozen rule codes cross into a model context, never hidden test inputs."""

from collections import Counter

from pydantic import JsonValue

from agent_workbench.repair_store.comparison_models import ComparisonRecord
from agent_workbench.repair_store.reproduction_models import ReproductionRecord, result_outcome


def reproduction_feedback(record: ReproductionRecord) -> dict[str, JsonValue]:
    report = record.report
    return {
        "status": result_outcome(
            report, record.versions_verified_after, baseline=record.plan.baseline
        )
        if report
        else record.status,
        "rule_failures": dict(Counter(s.code for s in report.steps if s.status == "failed"))
        if report
        else {},
        "report_available": report is not None,
        "cleanup": report.cleanup if report else "unconfirmed",
        "baseline_tree_hash": record.plan.baseline.tree_sha256,
    }


def comparison_feedback(record: ComparisonRecord) -> dict[str, JsonValue]:
    report = record.report
    return {
        "status": report.outcome if report else record.status,
        "reason": report.reason if report else "result_unavailable",
        "candidate_id": record.plan.candidate.snapshot_id,
        "candidate_tree_hash": record.plan.candidate.tree_sha256,
        "baseline_tree_hash": record.plan.baseline.tree_sha256,
        "rule_failures": dict(
            Counter(
                s.code
                for item in record.results
                if item.slot.startswith("candidate_")
                for s in item.report.steps
                if s.status == "failed"
            )
        ),
        "comparison_complete": len(record.results) == 4,
        "accepted": False,
    }
