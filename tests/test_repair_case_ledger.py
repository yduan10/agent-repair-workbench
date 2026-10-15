"""H2 real SQLite CAS/audit for both fixed profiles; reports here are synthetic DTOs."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.repair_cases.profiles import get_profile
from agent_workbench.repair_store.reproduction_models import ReproductionPlan, reproduction_id
from agent_workbench.repair_store.reproductions import ReproductionStore
from tests.test_repair_comparisons import cas, ctx, handles, item_for, reserve


@pytest.fixture(params=["output_mismatch", "counter_offset"])
def profile_context(tmp_path, request, monkeypatch):
    create = SnapshotStore.create_baseline
    case_id = request.param
    monkeypatch.setattr(
        SnapshotStore,
        "create_baseline",
        lambda self, snapshot_id: create(self, snapshot_id, case_id=case_id),
    )
    generator = ctx.__wrapped__(tmp_path, SimpleNamespace(param="three_role"))
    context = next(generator)
    yield case_id, context
    with pytest.raises(StopIteration):
        next(generator)


def profile_item(case_id, plan, index):
    item = item_for(plan, index)
    if index == 0:
        for step in item.report.steps:
            if step.status == "failed":
                step.code = get_profile(case_id).failure_code
    return item


def test_profile_reproduction_saved_and_audited(profile_context):
    case_id, context = profile_context
    original, fence, saved, comparison, baseline, _, image_root = context
    store = ReproductionStore(original.directory)
    try:
        request_id = str(uuid4())
        plan = ReproductionPlan(
            task_id=comparison.task_id,
            request_id=request_id,
            attempt_id=reproduction_id(comparison.task_id, request_id),
            baseline=baseline.ref,
            suite_sha256=comparison.suite_sha256,
            oracle_sha256=comparison.oracle_sha256,
            image_id=comparison.image_id,
            image_source_sha256=comparison.image_source_sha256,
        )
        pending = store.reserve_reproduction(
            plan,
            role="diagnosis",
            **cas(saved, fence),
            baseline=baseline,
            image_root=image_root,
        )
        report = profile_item(case_id, comparison, 0).report
        report.attempt_id = plan.attempt_id
        done = store.finish_reproduction(
            pending.claim,
            report,
            **cas(pending, fence),
            baseline=baseline,
            image_root=image_root,
        )
        assert done.task.phase == "ready" and done.request.status == "completed"
        assert store.get(plan.task_id).task == done.task
        assert store.get_reproduction(plan.task_id, request_id).report == report
        assert done.task.outcome is None  # A baseline failure never verifies a candidate.
    finally:
        store.close()


@pytest.mark.parametrize("swap_baseline_code", [False, True])
def test_profile_comparison_persisted_verdict_remains_exact(profile_context, swap_baseline_code):
    case_id, context = profile_context
    store, fence, _, plan, *_ = context
    pending = reserve(context)
    cursor = pending
    for index in range(4):
        item = profile_item(case_id, plan, index)
        if index == 0 and swap_baseline_code:
            for step in item.report.steps:
                if step.status == "failed":
                    step.code = "count_value" if case_id == "output_mismatch" else "count_type"
        cursor = store.save_slot(pending.claim, item, **cas(cursor, fence))
    done = store.finalize_comparison(pending.claim, **cas(cursor, fence), **handles(context))
    expected = "inconclusive" if swap_baseline_code else "candidate_verified"
    assert done.comparison.report.outcome == expected
    assert done.comparison.report.accepted is False
    assert store.get(plan.task_id).task == done.task


@pytest.mark.parametrize("mutation", ["none", "case_name", "manifest", "other_case"])
def test_tool_bridge_requires_same_durable_profile(profile_context, mutation):
    from agent_workbench.controlled_tools.resources import load_repair_case
    from agent_workbench.controlled_tools.responses import ResourceError
    from agent_workbench.repair_runtime.tools import RepairToolBridge

    case_id, context = profile_context
    original, fence, saved, _, baseline, _, image_root = context
    chosen = case_id
    if mutation == "other_case":
        chosen = "counter_offset" if case_id == "output_mismatch" else "output_mismatch"
    registry = load_repair_case(chosen, task_id=saved.task.task_id, budget=saved.task.budget)
    if mutation == "case_name":
        registry.case_name = "counter_offset" if case_id == "output_mismatch" else "output_mismatch"
    if mutation == "manifest":
        registry.manifest_sha256 = "a" * 64
    store = ReproductionStore(original.directory)
    try:

        def create():
            return RepairToolBridge(
                store=store,
                registry=registry,
                baseline=baseline,
                snapshots=SnapshotStore(baseline.root.parent),
                image_root=image_root,
                fence=fence,
                remaining_seconds=lambda: 600,
            )

        if mutation == "none":
            assert create().task_id == saved.task.task_id
        else:
            with pytest.raises(ResourceError, match="PERMISSION_DENIED"):
                create()
        assert store.get(saved.task.task_id).task == saved.task
    finally:
        store.close()
