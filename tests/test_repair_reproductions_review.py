"""Independent T05 storage probes; synthetic reports, real SQLite, no Docker."""

import sqlite3

import pytest

from agent_workbench.repair_store.reproduction_models import reproduction_id
from agent_workbench.run_store.models import StoreError
from tests.test_repair_comparisons import ctx as ctx
from tests.test_repair_comparisons import uid
from tests.test_repair_reproductions import counts, finish, report_for, reserve_t05
from tests.test_repair_reproductions import repro as repro


def test_settlement_event_failure_rolls_back_report_and_claim_is_retryable(repro):
    pending = reserve_t05(repro)
    before = counts(repro)
    with sqlite3.connect(repro[0]._base.path) as db:
        db.execute(
            "CREATE TRIGGER reviewer_failure BEFORE INSERT ON repair_events "
            "BEGIN SELECT RAISE(ABORT,'independent failure'); END"
        )
    with pytest.raises(StoreError):
        finish(repro, pending)
    assert counts(repro) == before
    assert repro[0].get(repro[3].task_id).task == pending.task
    assert repro[0].get_reproduction(repro[3].task_id, repro[3].request_id).report is None
    with sqlite3.connect(repro[0]._base.path) as db:
        db.execute("DROP TRIGGER reviewer_failure")
    done = finish(repro, pending)
    assert done.task.phase == "ready"
    assert done.task.usage.tool_calls == pending.task.usage.tool_calls
    assert finish(repro, pending).claim is None


def test_nested_report_mutation_is_revalidated_before_persist(repro):
    pending = reserve_t05(repro)
    report = report_for(repro)
    report.steps.clear()
    before = counts(repro)
    with pytest.raises(StoreError, match="invalid_repair_input"):
        finish(repro, pending, report)
    assert counts(repro) == before
    assert repro[0].get(repro[3].task_id).task == pending.task
    assert repro[0].get_reproduction(repro[3].task_id, repro[3].request_id).report is None


def test_t05_requests_share_task_tool_budget_without_role_reset(repro):
    original = repro[2]
    # One existing T06 charge leaves 19 slots in the shared 20-tool budget.
    assert original.task.usage.tool_calls == 1
    for _ in range(19):
        request_id = uid()
        plan = repro[3].model_copy(
            update={
                "request_id": request_id,
                "attempt_id": reproduction_id(repro[3].task_id, request_id),
            }
        )
        current = (*repro[:2], original, plan, *repro[4:])
        pending = reserve_t05(current)
        original = finish(current, pending)
    assert original.task.usage.tool_calls == 20
    request_id = uid()
    plan = repro[3].model_copy(
        update={
            "request_id": request_id,
            "attempt_id": reproduction_id(repro[3].task_id, request_id),
        }
    )
    before = counts(repro)
    with pytest.raises(StoreError, match="budget_exceeded"):
        reserve_t05(repro, saved=original, plan=plan)
    assert counts(repro) == before
    assert repro[0].get(repro[3].task_id).task == original.task


def test_same_named_but_replaced_guard_blocks_reads(repro):
    pending = reserve_t05(repro)
    with sqlite3.connect(repro[0]._base.path) as db:
        db.execute("DROP TRIGGER repair_reproduction_identity")
        db.execute(
            "CREATE TRIGGER repair_reproduction_identity "
            "AFTER INSERT ON repair_reproductions BEGIN SELECT 1; END"
        )
    with pytest.raises(StoreError, match="schema_incompatible"):
        repro[0].get_reproduction(pending.task.task_id, repro[3].request_id)
