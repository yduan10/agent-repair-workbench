"""P0-06 B1b: real SQLite transactions and owner processes, no model or execution."""

import multiprocessing
import os
import signal
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import update

from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.mcp_models import MCPReport
from agent_workbench.model_gateway.gateway import PreparedCall, Reply
from agent_workbench.models import Report
from agent_workbench.orchestration.contracts import Budget, Usage
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairClaim, RepairTask
from agent_workbench.repair_store.store import RepairStore
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.schema import (
    repair_candidates,
    repair_events,
    repair_requests,
    repair_tasks,
)
from agent_workbench.run_store.store import REVISION
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport


def finish(store, claim):
    report = SandboxReport(
        run_id=claim.run.attempt_id,
        record_id=claim.run.run_id,
        mcp=MCPReport(
            invocation_id="synthetic",
            adapter_outcome="completed",
            contract_report=Report(status="passed"),
        ),
        execution=ExecutionEvidence(cleanup="removed"),
    )
    return store.finish(
        claim.run.run_id,
        claim.run.attempt_id,
        claim.token,
        claim.run.version,
        "succeeded",
        report,
        "absent",
    )


def uid():
    return str(uuid4())


def cas(saved, fence):
    return dict(
        expected_revision=saved.task.revision, expected_sha256=saved.task_sha256, fence=fence
    )


@pytest.fixture
def ctx(tmp_path):
    clock = [1_700_000_000.0]
    store = RepairStore(tmp_path / "state", clock=lambda: clock[0])
    store.initialize()
    snapshots = SnapshotStore(tmp_path / "snapshots")
    baseline = snapshots.create_baseline(uid())
    task = RepairTask(
        task_id=uid(),
        baseline=baseline.ref,
        mode="three_role",
        started_at=datetime.fromtimestamp(clock[0], UTC),
        budget=Budget(total_tokens=10000, output_tokens=4096),
        model_config_sha256="a" * 64,
    )
    with RepairFence(store.directory, task.task_id) as fence:
        initial = store.create_task(task, fence=fence)
        yield store, fence, initial, snapshots, baseline, clock
    store.close()


def patch_for(base):
    return CandidatePatch(
        expected_baseline_hash=base.ref.tree_sha256,
        expected_file_hash=base.ref.file_sha256,
        replacement=(
            "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
            '    return {"count": count}\n'
        ),
    )


def reserve_candidate(ctx, saved=None, request=None, candidate=None, role="repair", patch=None):
    store, fence, initial, _, baseline, _ = ctx
    return store.reserve_candidate(
        initial.task.task_id,
        request or uid(),
        candidate or uid(),
        role,
        patch or patch_for(baseline),
        **cas(saved or initial, fence),
    )


def reserve_model(ctx, saved=None, request=None, role="diagnosis", prepared=None):
    store, fence, initial, *_ = ctx
    return store.reserve_model(
        initial.task.task_id,
        request or uid(),
        role,
        prepared or PreparedCall(b"PRIVATE MODEL PROMPT", "b" * 64, 100, 50, "c" * 64),
        **cas(saved or initial, fence),
    )


def test_candidate_publish_and_restart_and_public_value_boundary(ctx):
    store, fence, initial, snapshots, baseline, _ = ctx
    pending = reserve_candidate(ctx)
    assert pending.claim and pending.candidate.sequence == 1
    snapshot = snapshots.create_candidate(
        baseline, pending.candidate.candidate_id, patch_for(baseline)
    )
    committed = store.finish_candidate(pending.claim, snapshot=snapshot.ref, **cas(pending, fence))
    assert committed.candidate.status == "committed"
    assert committed.task.usage.tool_calls == 1
    store.close()
    reopened = RepairStore(store.directory)
    assert reopened.get(initial.task.task_id) == store.get(initial.task.task_id)
    assert reopened.candidates(initial.task.task_id) == [committed.candidate]
    with sqlite3.connect(store._base.path) as db:
        raw = b"".join(
            bytes(row[0])
            for name in ("repair_tasks", "repair_requests", "repair_events", "repair_candidates")
            for row in db.execute(f"SELECT payload FROM {name}")
        )
    assert pending.claim.token.encode() not in raw
    assert b"return {" not in raw and str(store.directory).encode() not in raw
    assert pending.claim.token not in repr(pending.claim)


def test_duplicate_before_cas_no_new_permission_and_different_payload_conflict(ctx):
    store, fence, initial, *_ = ctx
    req, cid = uid(), uid()
    pending = reserve_candidate(ctx, request=req, candidate=cid)
    repeated = reserve_candidate(ctx, request=req, candidate=cid)
    assert repeated.claim is None and repeated.task == pending.task
    with pytest.raises(StoreError, match="request_conflict"):
        reserve_candidate(ctx, request=req, candidate=uid())
    done = store.finish_candidate(pending.claim, error_code="INVALID_INPUT", **cas(pending, fence))
    ended = store.finish_task(initial.task.task_id, "failed", **cas(done, fence))
    repeated = reserve_candidate(ctx, request=req, candidate=cid)
    assert repeated.claim is None and repeated.task == ended.task


def test_two_attempts_count_failed_and_unknown_never_reauthorize(ctx):
    store, fence, _, *_ = ctx
    first = reserve_candidate(ctx)
    failed = store.finish_candidate(first.claim, error_code="INVALID_INPUT", **cas(first, fence))
    second = reserve_candidate(ctx, saved=failed)
    failed2 = store.finish_candidate(second.claim, error_code="INVALID_INPUT", **cas(second, fence))
    with pytest.raises(StoreError, match="candidate_limit"):
        reserve_candidate(ctx, saved=failed2)
    assert store.get(first.task.task_id).task.candidate_count == 2


@pytest.mark.parametrize("role", ["diagnosis", "verification", "single"])
def test_role_cannot_claim_candidate(ctx, role):
    with pytest.raises(StoreError, match="permission_denied"):
        reserve_candidate(ctx, role=role)


@pytest.mark.parametrize("change", ["stale", "other_file", "baseline_id"])
def test_baseline_binding(ctx, change):
    _, _, _, _, base, _ = ctx
    patch = patch_for(base)
    if change == "stale":
        patch = patch.model_copy(update={"expected_baseline_hash": "0" * 64})
    elif change == "other_file":
        patch = patch.model_copy(update={"path": "secret.py"})
    with pytest.raises(StoreError):
        reserve_candidate(
            ctx, patch=patch, candidate=base.ref.snapshot_id if change == "baseline_id" else None
        )


def test_model_reserve_settle_once_unknown_preserves_and_never_stores_reply(ctx):
    store, fence, initial, *_ = ctx
    pending = reserve_model(ctx)
    known = store.settle_model(
        pending.claim, Reply(b"PRIVATE RESPONSE", 15, 10), **cas(pending, fence)
    )
    assert known.task.usage.known_input_tokens == 15 and known.task.usage.reserved_tokens == 0
    with pytest.raises(StoreError, match="claim_conflict"):
        store.settle_model(pending.claim, Reply(None, 15, 10), **cas(known, fence))
    second = reserve_model(ctx, saved=known)
    unknown = store.settle_model(
        second.claim, Reply(error="provider private error"), **cas(second, fence)
    )
    assert unknown.task.outcome == "outcome_unknown"
    assert unknown.task.usage.reserved_tokens == 150 and unknown.task.usage.model_calls == 2
    duplicate = reserve_model(ctx, request=second.request.request_id)
    assert duplicate.claim is None
    with sqlite3.connect(store._base.path) as db:
        raw = b"".join(row[0] for row in db.execute("SELECT payload FROM repair_events"))
        assert b"PRIVATE" not in raw and b"provider private error" not in raw
    with pytest.raises(StoreError, match="repair_finished"):
        reserve_model(ctx, saved=unknown)


@pytest.mark.parametrize(
    "reply", [Reply(None, 101, 0), Reply(None, True, 1), Reply(None, 2, None), Reply(None, 0, 51)]
)
def test_invalid_usage_keeps_reservation(ctx, reply):
    store, fence, *_ = ctx
    pending = reserve_model(ctx)
    done = store.settle_model(pending.claim, reply, **cas(pending, fence))
    assert done.task.outcome == "outcome_unknown" and done.task.usage.reserved_tokens == 150


def test_budget_deadline_and_inflight_limits(ctx):
    store, fence, initial, _, _, clock = ctx
    pending = reserve_model(ctx)
    with pytest.raises(StoreError, match="request_pending"):
        reserve_model(ctx, saved=pending)
    with pytest.raises(StoreError, match="stale_version"):
        reserve_candidate(ctx)
    completed = store.settle_model(pending.claim, Reply(None, 1, 1), **cas(pending, fence))
    with pytest.raises(StoreError, match="budget_exceeded"):
        reserve_model(
            ctx, saved=completed, prepared=PreparedCall(b"", "b" * 64, 10000, 50, "c" * 64)
        )
    clock[0] += 601
    with pytest.raises(StoreError, match="deadline_exceeded"):
        reserve_model(ctx, saved=completed)
    assert store.get(initial.task.task_id).task == completed.task


def test_tool_permissions_and_cross_request_claim(ctx):
    store, fence, initial, *_ = ctx
    with pytest.raises(StoreError, match="permission_denied"):
        store.reserve_tool(
            initial.task.task_id, uid(), "repair", "T05", "b" * 64, **cas(initial, fence)
        )
    pending = store.reserve_tool(
        initial.task.task_id, uid(), "diagnosis", "T05", "b" * 64, **cas(initial, fence)
    )
    fake = RepairClaim(pending.claim.task_id, pending.claim.request_id, "forged")
    with pytest.raises(StoreError, match="claim_conflict"):
        store.finish_tool(fake, **cas(pending, fence))
    done = store.finish_tool(pending.claim, **cas(pending, fence))
    assert done.task.usage.tool_calls == 1
    with pytest.raises(StoreError, match="invalid_repair_input"):
        store.finish_task(initial.task.task_id, "candidate_verified", **cas(done, fence))


def test_atomic_failure_rolls_back_claim_budget_and_sequence(ctx):
    store, fence, initial, *_ = ctx
    with sqlite3.connect(store._base.path) as db:
        db.execute(
            "CREATE TRIGGER fail_event BEFORE INSERT ON repair_events "
            "BEGIN SELECT RAISE(ABORT, 'test'); END"
        )
    with pytest.raises(StoreError, match="store_unavailable"):
        reserve_candidate(ctx)
    assert store.get(initial.task.task_id).task == initial.task
    assert store.candidates(initial.task.task_id) == []


@pytest.mark.parametrize("table", [repair_tasks, repair_requests, repair_events, repair_candidates])
def test_row_digest_tampering_detected(ctx, table):
    store, _, initial, *_ = ctx
    reserve_candidate(ctx)
    with store._base._transaction(write=True) as db:
        db.execute(update(table).values(sha256="0" * 64))
    with pytest.raises(StoreError, match="store_corrupt"):
        store.get(initial.task.task_id)


def test_recomputed_task_digest_cannot_forge_usage(ctx):
    store, _, initial, *_ = ctx
    pending = reserve_model(ctx)
    task = pending.task.model_copy(
        update={"usage": pending.task.usage.model_copy(update={"model_calls": 2})}
    )
    raw = canonical(task.model_dump(mode="json"))
    with store._base._transaction(write=True) as db:
        db.execute(update(repair_tasks).values(payload=raw, sha256=digest(raw)))
        row = (
            db.execute(repair_events.select().where(repair_events.c.revision == 1)).mappings().one()
        )
        import json

        event = json.loads(row["payload"])
        event["task_sha256"] = digest(raw)
        data = canonical(event)
        db.execute(
            update(repair_events)
            .where(repair_events.c.revision == 1)
            .values(payload=data, sha256=digest(data))
        )
    with pytest.raises(StoreError, match="store_corrupt"):
        store.get(initial.task.task_id)


def hold_owner(directory, task_id, ready):
    with RepairFence(Path(directory), task_id):
        ready.set()
        signal.pause()


def test_paused_owner_blocks_recovery_then_kill_reconciles_without_replay(ctx, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    store, fence, _, *_ = ctx
    pending = reserve_candidate(ctx)
    fence.close()
    process = multiprocessing.get_context("spawn")
    ready = process.Event()
    owner = process.Process(
        target=hold_owner, args=(str(store.directory), pending.task.task_id, ready)
    )
    owner.start()
    try:
        assert ready.wait(10)
        os.kill(owner.pid, signal.SIGSTOP)
        with pytest.raises(StoreError, match="repair_busy"):
            store.reconcile(
                pending.task.task_id,
                expected_revision=pending.task.revision,
                expected_sha256=pending.task_sha256,
            )
        owner.kill()
        owner.join(5)
        result = store.reconcile(
            pending.task.task_id,
            expected_revision=pending.task.revision,
            expected_sha256=pending.task_sha256,
        )
        assert (
            result.task.outcome == "outcome_unknown"
            and result.candidate.status == "outcome_unknown"
        )
        with RepairFence(store.directory, pending.task.task_id) as new_fence:
            replay = store.reserve_candidate(
                pending.task.task_id,
                pending.request.request_id,
                pending.candidate.candidate_id,
                "repair",
                patch_for(ctx[4]),
                **cas(result, new_fence),
            )
            assert replay.claim is None
            with pytest.raises(StoreError, match="repair_finished"):
                store.finish_candidate(
                    pending.claim, error_code="INVALID_INPUT", **cas(result, new_fence)
                )
    finally:
        if owner.is_alive():
            owner.kill()
            owner.join(5)


def test_explicit_v3_upgrade_with_backup_preserves_all_old_rows(tmp_path):
    store = RepairStore(tmp_path / "state")
    store.initialize()
    base = store._base
    run = base.create("isolated-fixture", "pass", "a" * 64, "b" * 64)
    claim = base.claim(run.run_id, run.version)
    finish(base, claim)
    from agent_workbench.analysis_store.fencing import AnalysisFence
    from agent_workbench.analysis_store.models import AnalysisEvent
    from agent_workbench.analysis_store.store import AnalysisStore
    from agent_workbench.orchestration.contracts import AnalysisSummary, EvidenceRef, TaskState

    analysis = AnalysisStore(store.directory)
    analysis_id = uid()
    summary = AnalysisSummary(
        task_id=analysis_id,
        source_kind="synthetic",
        state=TaskState(task_id=analysis_id, intent="diagnose"),
        started_at=datetime.now(UTC),
        budget=Budget(total_tokens=1000, output_tokens=100),
        usage=Usage(),
        evidence_refs=(EvidenceRef(evidence_id=uid(), sha256="a" * 64),),
    )
    with AnalysisFence(store.directory, analysis_id) as owner:
        analysis.create(summary, AnalysisEvent(kind="created"), fence=owner)
    with base._transaction(write=True) as db:
        db.exec_driver_sql("INSERT INTO web_requests VALUES (?, ?, 0, 0)", (run.run_id, "c" * 64))
        command.downgrade(base._migration(db), "0003_analyses")
    names = (
        "runs",
        "attempts",
        "events",
        "artifacts",
        "web_requests",
        "analysis_summaries",
        "analysis_events",
        "analysis_execution_links",
    )
    with sqlite3.connect(base.path) as db, sqlite3.connect(tmp_path / "backup.sqlite3") as backup:
        db.backup(backup)
        before = {n: db.execute(f"SELECT * FROM {n} ORDER BY 1").fetchall() for n in names}
    with pytest.raises(StoreError, match="schema_incompatible"):
        base.list_runs()
    store.initialize()
    with sqlite3.connect(base.path) as db:
        assert before == {n: db.execute(f"SELECT * FROM {n} ORDER BY 1").fetchall() for n in names}
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (REVISION,)
    assert base.report(run.run_id).mcp.contract_report.status == "passed"


def test_single_role_mode_and_no_missing_analysis_source(ctx):
    store, _, initial, _, _, _ = ctx
    single = initial.task.model_copy(update={"task_id": uid(), "mode": "single_role"})
    with RepairFence(store.directory, single.task_id) as fence:
        saved = store.create_task(single, fence=fence)
        with pytest.raises(StoreError, match="permission_denied"):
            store.reserve_tool(
                single.task_id, uid(), "diagnosis", "T01", "a" * 64, **cas(saved, fence)
            )
        claimed = store.reserve_tool(
            single.task_id, uid(), "single", "T01", "a" * 64, **cas(saved, fence)
        )
        assert claimed.claim and claimed.task.budget == initial.task.budget
    invalid = initial.task.model_copy(update={"task_id": uid(), "source_analysis_id": uid()})
    with RepairFence(store.directory, invalid.task_id) as fence:
        with pytest.raises(StoreError, match="analysis_not_found"):
            store.create_task(invalid, fence=fence)
    with pytest.raises(StoreError, match="repair_not_found"):
        store.get(invalid.task_id)


def test_concurrent_identical_request_grants_exactly_once(ctx):
    from concurrent.futures import ThreadPoolExecutor

    store, _, initial, *_ = ctx
    request, candidate = uid(), uid()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: reserve_candidate(ctx, request=request, candidate=candidate), range(2)
            )
        )
    assert sum(result.claim is not None for result in results) == 1
    assert store.get(initial.task.task_id).task.candidate_count == 1


def test_finish_requires_exact_owned_candidate_snapshot(ctx):
    store, fence, _, snapshots, baseline, _ = ctx
    pending = reserve_candidate(ctx)
    valid = snapshots.create_candidate(
        baseline, pending.candidate.candidate_id, patch_for(baseline)
    )
    for change in (
        {"snapshot_id": uid()},
        {"baseline_id": uid()},
        {"patch_sha256": "0" * 64},
        {"manifest_sha256": "0" * 64},
    ):
        with pytest.raises(StoreError):
            store.finish_candidate(
                pending.claim, snapshot=valid.ref.model_copy(update=change), **cas(pending, fence)
            )
    assert store.get(pending.task.task_id).task.phase == "candidate_preparing"
    unknown = store.finish_candidate(
        pending.claim, error_code="TOOL_OUTCOME_UNKNOWN", **cas(pending, fence)
    )
    assert (
        unknown.task.outcome == "outcome_unknown" and unknown.candidate.status == "outcome_unknown"
    )


def test_recovery_keeps_model_reservation_and_prevents_old_claim(ctx):
    store, fence, *_ = ctx
    pending = reserve_model(ctx)
    fence.close()
    done = store.reconcile(
        pending.task.task_id,
        expected_revision=pending.task.revision,
        expected_sha256=pending.task_sha256,
    )
    assert done.task.usage == pending.task.usage
    with RepairFence(store.directory, pending.task.task_id) as owner:
        with pytest.raises(StoreError, match="repair_finished"):
            store.settle_model(pending.claim, Reply(None, 1, 1), **cas(done, owner))


@pytest.mark.parametrize("model", [True, False])
def test_all_calls_charged_and_limits_are_cumulative(ctx, model):
    store, fence, saved, *_ = ctx
    for _ in range(12 if model else 20):
        if model:
            pending = reserve_model(ctx, saved=saved)
            saved = store.settle_model(pending.claim, Reply(None, 1, 1), **cas(pending, fence))
        else:
            pending = store.reserve_tool(
                saved.task.task_id, uid(), "diagnosis", "T01", "a" * 64, **cas(saved, fence)
            )
            saved = store.finish_tool(pending.claim, **cas(pending, fence))
    with pytest.raises(StoreError, match="budget_exceeded"):
        if model:
            reserve_model(ctx, saved=saved)
        else:
            store.reserve_tool(
                saved.task.task_id, uid(), "diagnosis", "T01", "a" * 64, **cas(saved, fence)
            )
    assert store.get(saved.task.task_id).task.usage == saved.task.usage


def test_wrong_owner_and_terminal_rows_cannot_be_modified(ctx):
    store, fence, initial, *_ = ctx
    with RepairFence(store.directory, uid()) as wrong:
        with pytest.raises(StoreError, match="owner_lock_required"):
            store.reserve_tool(
                initial.task.task_id, uid(), "diagnosis", "T01", "a" * 64, **cas(initial, wrong)
            )
    done = store.finish_task(initial.task.task_id, "cancelled", **cas(initial, fence))
    with pytest.raises(StoreError, match="repair_finished"):
        store.finish_task(initial.task.task_id, "failed", **cas(done, fence))
    with pytest.raises(StoreError, match="migration_not_empty"):
        store._base.downgrade_empty()
