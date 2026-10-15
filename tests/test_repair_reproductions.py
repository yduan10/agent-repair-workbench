"""T05 ledger tests: real SQLite/snapshots; oracle evidence explicitly synthetic, no Docker."""

import sqlite3
from dataclasses import replace

import pytest
from alembic import command

from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.reproduction_models import ReproductionPlan, reproduction_id
from agent_workbench.repair_store.reproductions import ReproductionStore
from agent_workbench.repair_store.store import RepairStore
from agent_workbench.run_store.models import StoreError
from tests.test_repair_comparisons import cas, handles, item_for, reserve, uid
from tests.test_repair_comparisons import ctx as ctx


@pytest.fixture
def repro(ctx):
    original, fence, saved, cp, baseline, _, image_root = ctx
    store = ReproductionStore(original.directory)
    request_id = uid()
    plan = ReproductionPlan(
        task_id=cp.task_id,
        request_id=request_id,
        attempt_id=reproduction_id(cp.task_id, request_id),
        baseline=baseline.ref,
        suite_sha256=cp.suite_sha256,
        oracle_sha256=cp.oracle_sha256,
        image_id=cp.image_id,
        image_source_sha256=cp.image_source_sha256,
    )
    yield store, fence, saved, plan, baseline, image_root, ctx
    store.close()


def reserve_t05(repro, saved=None, plan=None, role="diagnosis"):
    store, fence, original, p, baseline, image, _ = repro
    return store.reserve_reproduction(
        plan or p, role=role, **cas(saved or original, fence), baseline=baseline, image_root=image
    )


def report_for(repro):
    report = item_for(repro[-1][3], 0).report
    report.attempt_id = repro[3].attempt_id
    return report


def finish(repro, pending, report=None):
    return repro[0].finish_reproduction(
        pending.claim,
        report or report_for(repro),
        **cas(pending, repro[1]),
        baseline=repro[4],
        image_root=repro[5],
    )


def counts(repro):
    with sqlite3.connect(repro[0]._base.path) as c:
        return tuple(
            c.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for name in (
                "repair_reproductions",
                "repair_execution_identities",
                "repair_requests",
                "repair_events",
            )
        )


def test_reserve_replay_and_finish_are_single_charge(repro):
    pending = reserve_t05(repro)
    assert pending.claim and pending.request.operation == "reproduction"
    assert pending.task.usage.tool_calls == repro[2].task.usage.tool_calls + 1
    assert pending.reproduction.plan.attempt_id == reproduction_id(
        repro[3].task_id, repro[3].request_id
    )
    before = counts(repro)
    replay = reserve_t05(repro)  # Stale CAS is intentionally allowed for exact read-only replay.
    assert replay.claim is None and replay.task == pending.task
    assert counts(repro) == before
    done = finish(repro, pending)
    assert done.task.phase == "ready" and done.request.status == "completed"
    assert done.task.outcome is None
    assert reserve_t05(repro).claim is None
    assert finish(repro, pending).task == done.task
    assert repro[0].get_reproduction(repro[3].task_id, repro[3].request_id) == done.reproduction


@pytest.mark.parametrize(
    "field,value", [("oracle_sha256", "a" * 64), ("image_id", "sha256:" + "b" * 64)]
)
def test_request_same_id_different_plan_conflicts(repro, field, value):
    reserve_t05(repro)
    with pytest.raises(StoreError, match="request_conflict"):
        reserve_t05(repro, plan=repro[3].model_copy(update={field: value}))


def test_permissions_and_generic_bypass(repro):
    with pytest.raises(StoreError, match="permission_denied"):
        reserve_t05(repro, role="repair")
    with pytest.raises(StoreError, match="reproduction_reservation_required"):
        repro[0].reserve_tool(
            repro[3].task_id, uid(), "diagnosis", "T05", "a" * 64, **cas(repro[2], repro[1])
        )


@pytest.mark.parametrize(
    "mutation", ["link_delete", "identity_delete", "identity_owner", "payload", "extra_identity"]
)
def test_audit_rejects_tampering_even_base_store_read(repro, mutation):
    reserve_t05(repro)
    with sqlite3.connect(repro[0]._base.path) as c:
        statements = {
            "link_delete": "DELETE FROM repair_reproductions",
            "identity_delete": "DELETE FROM repair_execution_identities",
            "identity_owner": "UPDATE repair_execution_identities SET owner_id='wrong'",
            "payload": "UPDATE repair_reproductions SET payload=x'7b7d'",
        }
        if mutation == "extra_identity":
            c.execute(
                "INSERT INTO repair_execution_identities VALUES (?, 'reproduction', ?)",
                (uid(), repro[3].task_id + ":" + uid()),
            )
        else:
            c.execute(statements[mutation])
    with pytest.raises(StoreError, match="store_corrupt"):
        RepairStore(repro[0].directory).get(repro[3].task_id)


@pytest.mark.parametrize("stage", ["insert", "event"])
def test_transaction_failure_rolls_back_identity_budget_and_link(repro, stage):
    table = "repair_reproductions" if stage == "insert" else "repair_events"
    with sqlite3.connect(repro[0]._base.path) as c:
        c.execute(
            f"CREATE TRIGGER injected_failure BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT,'test'); END"
        )
    before = counts(repro)
    with pytest.raises(StoreError):
        reserve_t05(repro)
    assert counts(repro) == before
    assert repro[0].get(repro[3].task_id).task == repro[2].task


def test_missing_guard_blocks_before_admission(repro):
    with sqlite3.connect(repro[0]._base.path) as c:
        c.execute("DROP TRIGGER repair_reproduction_identity")
    with pytest.raises(StoreError, match="schema_incompatible"):
        reserve_t05(repro)


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", uid()),
        ("snapshot_file_sha256", "b" * 64),
        ("scenario", "pass"),
        ("image_id", "sha256:" + "b" * 64),
    ],
)
def test_report_binding_rejected_atomically(repro, field, value):
    pending = reserve_t05(repro)
    report = report_for(repro)
    setattr(report, field, value)
    with pytest.raises(StoreError, match="invalid_repair_input"):
        finish(repro, pending, report)
    assert repro[0].get(repro[3].task_id).task == pending.task


def test_forged_claim_and_stale_cas_rejected(repro):
    pending = reserve_t05(repro)
    with pytest.raises(StoreError, match="claim_conflict"):
        finish(repro, replace(pending, claim=replace(pending.claim, token="fake")))
    with pytest.raises(StoreError, match="stale_version"):
        finish(repro, replace(pending, task=repro[2].task, task_sha256=repro[2].task_sha256))


@pytest.mark.parametrize(
    "status,cleanup,expected",
    [
        ("cancelled", "removed", "cancelled"),
        ("outcome_unknown", "removed", "outcome_unknown"),
        ("failed", "unconfirmed", "outcome_unknown"),
        ("inconclusive", "removed", "inconclusive"),
    ],
)
def test_terminal_fault_does_not_enable_another_execution(repro, status, cleanup, expected):
    pending = reserve_t05(repro)
    report = report_for(repro)
    report.status, report.cleanup = status, cleanup
    done = finish(repro, pending, report)
    assert done.task.outcome == expected and done.task.phase == "finished"
    assert reserve_t05(repro).claim is None


def test_unexpected_baseline_failure_or_version_change_inconclusive(repro):
    pending = reserve_t05(repro)
    (repro[5] / "containers/p0_06/supervisor.py").write_text("changed")
    done = finish(repro, pending)
    assert not done.reproduction.versions_verified_after
    assert done.task.outcome == "inconclusive"


def test_crash_recovery_keeps_identity_and_never_reissues_claim(repro):
    pending = reserve_t05(repro)
    with pytest.raises(StoreError, match="repair_busy"):
        repro[0].reconcile_reproduction(
            repro[3].task_id,
            expected_revision=pending.task.revision,
            expected_sha256=pending.task_sha256,
        )
    repro[1].close()
    with pytest.raises(StoreError, match="reproduction_recovery_required"):
        repro[0].reconcile(
            repro[3].task_id,
            expected_revision=pending.task.revision,
            expected_sha256=pending.task_sha256,
        )
    done = repro[0].reconcile_reproduction(
        repro[3].task_id,
        expected_revision=pending.task.revision,
        expected_sha256=pending.task_sha256,
    )
    assert done.task.outcome == "outcome_unknown"
    assert done.reproduction.plan == pending.reproduction.plan
    with RepairFence(repro[0].directory, repro[3].task_id) as fence:
        replay = repro[0].reserve_reproduction(
            repro[3], role="diagnosis", **cas(done, fence), baseline=repro[4], image_root=repro[5]
        )
        assert replay.claim is None


def test_t05_then_t07_identity_collision_rolls_back_all_four(repro):
    pending = reserve_t05(repro)
    done = finish(repro, pending)
    ctx = repro[-1]
    cp = ctx[3].model_copy(update={"attempts": (uid(), uid(), repro[3].attempt_id, uid())})
    before = counts(repro)
    with pytest.raises(StoreError):
        repro[0].reserve_comparison(cp, role="verification", **cas(done, repro[1]), **handles(ctx))
    assert counts(repro) == before
    assert repro[0].get(repro[3].task_id).task == done.task


def test_t07_then_t05_collision_is_global_across_tasks(repro):
    ctx = repro[-1]
    cp = ctx[3].model_copy(update={"attempts": (repro[3].attempt_id, uid(), uid(), uid())})
    pending = reserve(ctx, plan=cp)
    claim = pending.claim
    for index in range(4):
        pending = ctx[0].save_slot(claim, item_for(cp, index, "reject"), **cas(pending, ctx[1]))
    done = ctx[0].finalize_comparison(claim, **cas(pending, ctx[1]), **handles(ctx))
    assert done.task.phase == "ready"
    before = counts(repro)
    with pytest.raises(StoreError):
        reserve_t05(repro, saved=done)
    assert counts(repro) == before
    assert repro[0].get(repro[3].task_id).task == done.task


def _downgrade_0005(store):
    with store._base._transaction(write=True) as c:
        command.downgrade(store._base._migration(c), "0005_comparisons")


def test_migration_backfills_existing_comparison_identities(ctx):
    pending = reserve(ctx)
    store = ctx[0]
    _downgrade_0005(store)
    with sqlite3.connect(store._base.path) as c:
        before = c.execute("SELECT payload,sha256 FROM repair_tasks").fetchall()
    store.initialize()
    assert store.get(ctx[3].task_id).task == pending.task
    with sqlite3.connect(store._base.path) as c:
        assert c.execute("SELECT payload,sha256 FROM repair_tasks").fetchall() == before
        assert c.execute("SELECT count(*) FROM repair_execution_identities").fetchone()[0] == 4


def test_migration_duplicate_backfill_rolls_back_ddl_and_revision(ctx):
    reserve(ctx)
    store = ctx[0]
    _downgrade_0005(store)
    # Corrupt old schema: duplicate execution IDs cannot be silently accepted at migration.
    with sqlite3.connect(store._base.path) as c:
        c.execute("ALTER TABLE repair_comparison_attempts RENAME TO old_attempts")
        c.execute("CREATE TABLE repair_comparison_attempts AS SELECT * FROM old_attempts")
        c.execute("INSERT INTO repair_comparison_attempts SELECT * FROM old_attempts LIMIT 1")
        c.execute("DROP TABLE old_attempts")
    with pytest.raises(StoreError):
        store.initialize()
    with sqlite3.connect(store._base.path) as c:
        assert (
            c.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_comparisons"
        )
        assert not c.execute(
            "SELECT 1 FROM sqlite_master WHERE name='repair_execution_identities'"
        ).fetchall()
        assert not c.execute(
            "SELECT 1 FROM sqlite_master WHERE name='repair_reproductions'"
        ).fetchall()


def test_old_generic_t05_canonical_bytes_unchanged(ctx):
    store, fence, saved, cp, *_ = ctx
    old = store.reserve_tool(cp.task_id, uid(), "diagnosis", "T05", "a" * 64, **cas(saved, fence))
    old = store.finish_tool(old.claim, **cas(old, fence))
    _downgrade_0005(store)
    with sqlite3.connect(store._base.path) as c:
        before = {
            name: c.execute(f"SELECT payload,sha256 FROM {name}").fetchall()
            for name in ("repair_tasks", "repair_requests", "repair_events", "repair_candidates")
        }
    store.initialize()
    reader = ReproductionStore(store.directory)
    assert reader.get(cp.task_id).task == old.task
    with sqlite3.connect(store._base.path) as c:
        for name, records in before.items():
            assert c.execute(f"SELECT payload,sha256 FROM {name}").fetchall() == records
    reader.close()


@pytest.mark.parametrize("ctx", ["single_role"], indirect=True)
def test_single_role_has_same_t05_admission(repro):
    pending = reserve_t05(repro, role="single")
    assert pending.claim and pending.task.usage.tool_calls == repro[2].task.usage.tool_calls + 1


@pytest.mark.parametrize("mode", ["image", "snapshot", "oracle", "deadline"])
def test_admission_fails_closed_before_any_charge(repro, mode, monkeypatch):
    before = counts(repro)
    if mode == "image":
        (repro[5] / "artifacts/p0-06-image.json").unlink()
    elif mode == "snapshot":
        path = repro[4].root / "server.py"
        path.chmod(0o600)
        path.write_text("changed")
    elif mode == "oracle":
        monkeypatch.setattr(
            "agent_workbench.repair_store.reproductions.verify_oracle", lambda: False
        )
    else:
        expired = repro[2].task.started_at.timestamp() + repro[2].task.budget.timeout_seconds
        monkeypatch.setattr(repro[0]._base, "clock", lambda: expired)
    with pytest.raises(StoreError, match="version_mismatch|deadline_exceeded"):
        reserve_t05(repro)
    assert counts(repro) == before


def test_incomplete_or_wrong_failure_not_baseline_reproduction(repro):
    pending = reserve_t05(repro)
    report = report_for(repro)
    report.steps[2].code = "count_value"
    done = finish(repro, pending, report)
    assert done.task.outcome == "inconclusive"


def test_deleted_t07_identity_detected_by_original_comparison_store(ctx):
    reserve(ctx)
    with sqlite3.connect(ctx[0]._base.path) as c:
        c.execute(
            "DELETE FROM repair_execution_identities WHERE attempt_id=?", (ctx[3].attempts[0],)
        )
    with pytest.raises(StoreError, match="store_corrupt"):
        ctx[0].get(ctx[3].task_id)
