"""P1-01a W02/04/05/06/07: real SQLite and process fences, synthetic reports."""

import multiprocessing
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command

from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Report
from agent_workbench.run_store.execution import reconcile_runs
from agent_workbench.run_store.models import Claim, StoreError
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from agent_workbench.web_runs.fencing import OwnerFence
from agent_workbench.web_runs.models import ReproductionRequest
from agent_workbench.web_runs.store import WebRunStore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def store(tmp_path):
    store = WebRunStore(tmp_path / "state")
    store.initialize()
    yield store
    store.close()


def request(run_id=None, scenario="pass"):
    return ReproductionRequest(request_id=run_id or str(uuid4()), scenario=scenario)


def finish(store, claim, *, cleanup="removed", error=None):
    report = SandboxReport(
        run_id=claim.run.attempt_id,
        record_id=claim.run.run_id,
        mcp=MCPReport(
            invocation_id="synthetic",
            adapter_outcome="completed",
            contract_report=Report(status="passed"),
        ),
        execution=ExecutionEvidence(cleanup=cleanup, error=error),
    )
    return store.finish(
        claim.run.run_id,
        claim.run.attempt_id,
        claim.token,
        2,
        "succeeded" if cleanup == "removed" and error is None else "outcome_unknown",
        report,
        "absent" if cleanup == "removed" else "unavailable",
    )


def test_atomic_admit_replay_conflict_and_private_claim(store):
    req = request()
    with OwnerFence(store.directory) as fence:
        claim = store.admit(req, fence)
        assert isinstance(claim, Claim)
        assert claim.run.run_id == req.request_id and claim.run.status == "running"
        assert [event.kind for event in store.detail(req.request_id).events] == [
            "created",
            "claimed",
        ]
        assert store.admit(req, fence) == claim.run
        assert store.existing(req) == claim.run
        with pytest.raises(StoreError, match="^request_conflict$"):
            store.existing(request(req.request_id, "timeout"))
        with pytest.raises(StoreError, match="^runner_busy$"):
            store.admit(request(), fence)
        assert claim.token not in store.detail(req.request_id).model_dump_json()
        assert store.active_id() == req.request_id
        assert len(store.list_runs()) == 1


def test_atomic_rollback_when_claim_or_mapping_fails(store, monkeypatch):
    req = request()
    original = store._claim

    def fail(*args, **kwargs):
        raise StoreError("synthetic_claim_failure")

    monkeypatch.setattr(store, "_claim", fail)
    with OwnerFence(store.directory) as fence:
        with pytest.raises(StoreError):
            store.admit(req, fence)
        assert store.list_runs() == [] and store.active_id() is None
        monkeypatch.setattr(store, "_claim", original)
        with store._transaction(write=True) as c:
            c.exec_driver_sql(
                "CREATE TRIGGER reject_mapping BEFORE INSERT ON web_requests "
                "BEGIN SELECT RAISE(ABORT, 'synthetic'); END"
            )
        with pytest.raises(StoreError):
            store.admit(req, fence)
        assert store.list_runs() == [] and store.active_id() is None
        with store._transaction() as c:
            assert c.exec_driver_sql("SELECT COUNT(*) FROM attempts").scalar() == 0
            assert c.exec_driver_sql("SELECT COUNT(*) FROM events").scalar() == 0


def test_cancel_persistent_and_idempotent(store):
    req = request()
    with OwnerFence(store.directory) as fence:
        claim = store.admit(req, fence)
        other = WebRunStore(store.directory)
        assert not other.cancellation_requested(req.request_id)
        assert other.request_cancel(req.request_id)
        assert other.request_cancel(req.request_id)
        assert store.cancellation_requested(req.request_id)
        finish(store, claim)
        assert not other.request_cancel(req.request_id)
        assert store.release_safe(fence)
        other.close()
    with pytest.raises(StoreError, match="^web_run_not_found$"):
        store.request_cancel(str(uuid4()))


@pytest.mark.parametrize("mode", ["missing_report", "cleanup", "save_failed"])
def test_slot_retained_without_durable_safe_evidence(store, mode):
    req = request()
    with OwnerFence(store.directory) as fence:
        claim = store.admit(req, fence)
        if mode == "cleanup":
            finish(store, claim, cleanup="unconfirmed", error="cleanup_unconfirmed")
        elif mode == "missing_report":
            finish(store, claim)
            with store._transaction(write=True) as c:
                c.exec_driver_sql("DELETE FROM artifacts")
        if mode == "missing_report":
            with pytest.raises(StoreError, match="^report_not_found$"):
                store.release_safe(fence)
        else:
            assert not store.release_safe(fence)
        assert store.active_id() == req.request_id


def test_prune_excludes_active_then_retains_tombstone(store):
    now = [1_000_000.0]
    store.clock = lambda: now[0]
    req = request()
    with OwnerFence(store.directory) as fence:
        claim = store.admit(req, fence)
        finish(store, claim)
        now[0] += 31 * 86400
        assert store.prune(apply=True) == []
        assert store.release_safe(fence)
        assert store.prune(apply=True) == [req.request_id]
        with pytest.raises(StoreError, match="^request_gone$"):
            store.admit(req, fence)
        with pytest.raises(StoreError, match="^request_conflict$"):
            store.admit(request(req.request_id, "timeout"), fence)
        with pytest.raises(StoreError, match="^migration_not_empty$"):
            store.downgrade_empty()


def child_admit(directory, run_id, scenario, barrier, queue):
    store = WebRunStore(Path(directory))
    barrier.wait()
    try:
        req = request(run_id, scenario)
        existing = store.existing(req)
        if existing:
            queue.put(("reused", existing.run_id))
            return
        with OwnerFence(store.directory) as fence:
            result = store.admit(req, fence)
            queue.put(
                (
                    "claimed" if isinstance(result, Claim) else "reused",
                    result.run.run_id if isinstance(result, Claim) else result.run_id,
                )
            )
    except StoreError as exc:
        queue.put((exc.code, None))
    finally:
        store.close()


@pytest.mark.parametrize("same", [True, False])
def test_two_processes_admit_at_most_one_attempt(store, same, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    ctx = multiprocessing.get_context("spawn")
    queue, barrier = ctx.Queue(), ctx.Barrier(2)
    run_id = str(uuid4())
    processes = [
        ctx.Process(
            target=child_admit,
            args=(
                str(store.directory),
                run_id if same or i == 0 else str(uuid4()),
                "pass",
                barrier,
                queue,
            ),
        )
        for i in range(2)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(10)
        assert p.exitcode == 0
    results = [queue.get(timeout=1)[0] for _ in processes]
    assert results.count("claimed") == 1
    assert all(result in ("claimed", "reused", "runner_busy") for result in results)
    assert len(store.list_runs()) == 1
    with store._transaction() as c:
        assert c.exec_driver_sql("SELECT COUNT(*) FROM attempts").scalar() == 1


def child_probe_lock(directory, queue):
    try:
        with OwnerFence(Path(directory)):
            queue.put("acquired")
    except StoreError as exc:
        queue.put(exc.code)


@pytest.mark.anyio
async def test_paused_owner_lease_expired_blocks_reconcile_and_admission(store, monkeypatch):
    from agent_workbench.run_store import execution

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))

    now = [1000.0]
    store.clock = lambda: now[0]
    req = request()
    observed = []

    class Docker:
        async def inspect(self, name):
            observed.append(name)
            return None

    async def connect():
        return Docker()

    monkeypatch.setattr(execution.DockerControl, "connect", connect)
    with OwnerFence(store.directory) as fence:
        claim = store.admit(req, fence)
        now[0] += 121
        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        p = ctx.Process(target=child_probe_lock, args=(str(store.directory), q))
        p.start()
        p.join(10)
        assert p.exitcode == 0 and q.get(timeout=1) == "runner_busy"
        assert await reconcile_runs(store) == []
        assert observed == [] and store.detail(req.request_id).run.status == "running"
        with pytest.raises(StoreError, match="^runner_busy$"):
            store.admit(request(), fence)
        with pytest.raises(StoreError, match="^version_conflict$"):
            finish(store, claim)  # resumed stale owner cannot falsely commit success
    # Owner exited: explicit reconciliation can now inspect and record absence.
    reconciled = await reconcile_runs(store)
    assert reconciled[0].status == "outcome_unknown" and len(observed) == 1
    with OwnerFence(store.directory) as fence:
        new = store.admit(request(), fence)
        assert isinstance(new, Claim)
        assert store.existing(req).status == "outcome_unknown"


def test_requires_fence_and_rejects_symlink(store, tmp_path):
    fence = OwnerFence(store.directory)
    with pytest.raises(StoreError, match="^owner_lock_required$"):
        store.admit(request(), fence)
    (store.directory / "web-owner.lock").symlink_to(tmp_path / "unrelated")
    with pytest.raises(StoreError, match="^locking_unavailable$"):
        fence.acquire()
    assert not (tmp_path / "unrelated").exists()


def test_upgrade_old_data_backup_restore_and_unknown_revision(tmp_path):
    directory = tmp_path / "state"
    directory.mkdir()
    store = WebRunStore(directory)
    sqlite3.connect(store.path).close()
    with store._database().connect() as c:
        c.exec_driver_sql("BEGIN IMMEDIATE")
        command.upgrade(store._migration(c), "0001_run_store")
        c.exec_driver_sql(
            "INSERT INTO runs (run_id,status,version,created_at,updated_at,profile,"
            "scenario,config_sha256,case_sha256) VALUES "
            "('old','queued',1,1,1,'isolated-fixture','pass',?,?)",
            ("a" * 64, "b" * 64),
        )
        c.commit()
    with sqlite3.connect(store.path) as old, sqlite3.connect(tmp_path / "backup.sqlite3") as backup:
        old.backup(backup)
        before = old.execute("SELECT * FROM runs").fetchall()
    with pytest.raises(StoreError, match="^schema_incompatible$"):
        store.list_runs()
    store.initialize()
    with store._transaction() as c:
        assert [tuple(r) for r in c.exec_driver_sql("SELECT * FROM runs")] == before
    with pytest.raises(StoreError, match="^migration_not_empty$"):
        store.downgrade_empty()
    store.close()
    with (
        sqlite3.connect(tmp_path / "backup.sqlite3") as backup,
        sqlite3.connect(store.path) as restored,
    ):
        backup.backup(restored)
        assert restored.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0001_run_store",
        )
        assert restored.execute("SELECT * FROM runs").fetchall() == before
    store.initialize()
    with store._transaction(write=True) as c:
        c.exec_driver_sql("UPDATE alembic_version SET version_num='future'")
    with pytest.raises(StoreError, match="^schema_incompatible$"):
        store.initialize()
    store.close()


def test_cli_id_collision_does_not_acquire_web_identity(store):
    cli = store.create("isolated-fixture", "pass", "0" * 64, "1" * 64)
    with OwnerFence(store.directory) as fence:
        with pytest.raises(StoreError, match="^request_conflict$"):
            store.admit(request(cli.run_id), fence)
    assert store.active_id() is None
    assert store.existing(request(cli.run_id)) is None
    assert store.detail(cli.run_id).run.status == "queued"
    with pytest.raises(StoreError, match="^web_run_not_found$"):
        store.request_cancel(cli.run_id)
