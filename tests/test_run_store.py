from __future__ import annotations

import sqlite3
import stat
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.mcp_config import canonical, digest
from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Report
from agent_workbench.run_store import Claim, RunStore, StoreError
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport


@pytest.fixture
def clock() -> list[float]:
    return [1_000_000.0]


@pytest.fixture
def store(tmp_path: Path, clock: list[float]) -> RunStore:
    result = RunStore(tmp_path / "db", clock=lambda: clock[0])
    result.initialize()
    return result


def queued(store: RunStore):
    return store.create("isolated-fixture", "pass", "a" * 64, "b" * 64)


def claimed(store: RunStore) -> Claim:
    run = queued(store)
    return store.claim(run.run_id, run.version)


def report_for(claim: Claim) -> SandboxReport:
    assert claim.run.attempt_id is not None
    return SandboxReport(
        run_id=claim.run.attempt_id,
        record_id=claim.run.run_id,
        mcp=MCPReport(
            invocation_id="synthetic",
            adapter_outcome="completed",
            contract_report=Report(status="passed"),
        ),
        execution=ExecutionEvidence(cleanup="removed"),
    )


def finish(store: RunStore, claim: Claim, **kwargs):
    return store.finish(
        claim.run.run_id,
        claim.run.attempt_id,
        claim.token,
        claim.run.version,
        kwargs.pop("status", "succeeded"),
        kwargs.pop("report", report_for(claim)),
        kwargs.pop("executor_state", "absent"),
        **kwargs,
    )


def sql(store: RunStore, statement: str, params=()):
    with sqlite3.connect(store.path) as connection:
        return connection.execute(statement, params).fetchall()


def test_missing_reads_do_not_create(tmp_path: Path):
    store = RunStore(tmp_path / "missing")
    assert store.list_runs() == store.expired() == store.prune() == []
    for read in (store.detail, store.report):
        with pytest.raises(StoreError, match="^not_found$"):
            read(str(uuid4()))
    assert not store.directory.exists()


def test_restart_atomic_report_and_private_token(store: RunStore):
    claim = claimed(store)
    run = finish(store, claim)
    store.close()
    reopened = RunStore(store.directory)
    assert reopened.detail(run.run_id).run == run
    assert [e.kind for e in reopened.detail(run.run_id).events] == [
        "created",
        "claimed",
        "finished",
    ]
    raw = canonical(reopened.report(run.run_id).model_dump(mode="json"))
    assert digest(raw) == run.report_sha256
    assert claim.token not in reopened.detail(run.run_id).model_dump_json()
    assert "lease_token" not in reopened.detail(run.run_id).model_dump_json()
    assert sql(store, "SELECT size,payload FROM artifacts") == [(len(raw), raw)]


def test_permissions_and_sqlite_policies(store: RunStore):
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    with store._database().connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 2
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 1000
        for suffix in ("-wal", "-shm"):
            assert stat.S_IMODE(Path(str(store.path) + suffix).stat().st_mode) == 0o600


def test_migration_roundtrip_and_no_data_loss(store: RunStore):
    store.downgrade_empty()
    store.initialize()
    run = queued(store)
    with pytest.raises(StoreError, match="^migration_not_empty$"):
        store.downgrade_empty()
    assert store.detail(run.run_id).run == run
    sql(store, "UPDATE alembic_version SET version_num='9999_future'")
    for operation in (store.initialize, store.list_runs, store.downgrade_empty):
        with pytest.raises(StoreError, match="^schema_incompatible$"):
            operation()
    assert sql(store, "SELECT count(*) FROM runs") == [(1,)]


@pytest.mark.parametrize("kind", ["version", "token", "attempt", "expired"])
def test_stale_finish_never_changes_run(store: RunStore, clock: list[float], kind: str):
    claim = claimed(store)
    report = report_for(claim)
    attempt = claim.run.attempt_id
    token, version = claim.token, claim.run.version
    if kind == "version":
        version -= 1
    elif kind == "token":
        token = "stale"
    elif kind == "attempt":
        attempt = str(uuid4())
        report.run_id = attempt
    else:
        clock[0] += 120
    with pytest.raises(StoreError, match="^version_conflict$"):
        store.finish(claim.run.run_id, attempt, token, version, "succeeded", report, "absent")
    assert store.detail(claim.run.run_id).run == claim.run
    assert sql(store, "SELECT count(*) FROM artifacts") == [(0,)]
    assert len(store.detail(claim.run.run_id).events) == 2


def test_claim_is_not_reissued(store: RunStore):
    claim = claimed(store)
    for version in (1, 2):
        with pytest.raises(StoreError, match="^version_conflict$"):
            store.claim(claim.run.run_id, version)
    assert sql(store, "SELECT count(*) FROM attempts") == [(1,)]


def test_event_replay_and_conflict(store: RunStore, clock: list[float]):
    claim = claimed(store)
    event_id = str(uuid4())
    terminal = finish(store, claim, event_id=event_id)
    clock[0] += 1000
    assert finish(store, claim, event_id=event_id) == terminal
    with pytest.raises(StoreError, match="^event_conflict$"):
        finish(store, claim, status="outcome_unknown", event_id=event_id)
    assert len(store.detail(claim.run.run_id).events) == 3


@pytest.mark.parametrize("table", ["artifacts", "events"])
def test_real_sql_write_failure_rolls_back_terminal_report_and_event(store: RunStore, table: str):
    claim = claimed(store)
    sql(
        store,
        f"CREATE TRIGGER fail_write BEFORE INSERT ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'PRIVATE'); END",
    )
    with pytest.raises(StoreError, match="^store_unavailable$") as caught:
        finish(store, claim)
    assert "PRIVATE" not in str(caught.value)
    assert store.detail(claim.run.run_id).run == claim.run
    assert len(store.detail(claim.run.run_id).events) == 2
    assert sql(store, "SELECT count(*) FROM artifacts") == [(0,)]
    assert sql(store, "SELECT status FROM attempts") == [("running",)]


@pytest.mark.parametrize("mutation", ["size", "hash", "blob", "schema", "identity"])
def test_report_integrity(store: RunStore, mutation: str):
    claim = claimed(store)
    run = finish(store, claim)
    if mutation == "size":
        sql(store, "UPDATE artifacts SET size=size+1")
    elif mutation == "hash":
        sql(store, "UPDATE artifacts SET sha256='invalid'")
    elif mutation == "blob":
        sql(store, "UPDATE artifacts SET payload=?", (b"{}",))
    else:
        data = report_for(claim).model_dump(mode="json")
        if mutation == "schema":
            data["injected"] = "PRIVATE"
        else:
            data["record_id"] = str(uuid4())
        raw = canonical(data)
        sha = digest(raw)
        sql(store, "UPDATE artifacts SET payload=?,size=?,sha256=?", (raw, len(raw), sha))
        sql(store, "UPDATE runs SET report_sha256=?", (sha,))
    with pytest.raises(StoreError, match="^report_corrupt$"):
        store.report(run.run_id)


@pytest.mark.parametrize("mutation", ["association", "oversize", "false_success", "unclean"])
def test_invalid_report_or_status_rejected(store: RunStore, mutation: str):
    claim = claimed(store)
    report = report_for(claim)
    if mutation == "association":
        report.record_id = str(uuid4())
    elif mutation == "oversize":
        report.mcp.invocation_id = "x" * 1_048_576
    elif mutation == "false_success":
        report.mcp.adapter_outcome = "tool_error"
    else:
        report.execution.cleanup = "unconfirmed"
    with pytest.raises(StoreError, match="^invalid_(report|status)$"):
        finish(store, claim, report=report)
    assert store.detail(claim.run.run_id).run == claim.run


def test_reconcile_no_retry_late_commit_and_unknown_retained(store: RunStore, clock: list[float]):
    claim = claimed(store)
    with pytest.raises(StoreError, match="^version_conflict$"):
        store.reconcile(claim.run.run_id, claim.run.version, "unavailable")
    clock[0] += 120
    assert store.expired() == [claim.run]
    event_id = str(uuid4())
    unknown = store.reconcile(claim.run.run_id, claim.run.version, "unavailable", event_id=event_id)
    assert (
        store.reconcile(claim.run.run_id, claim.run.version, "unavailable", event_id=event_id)
        == unknown
    )
    assert store.expired() == [unknown]
    with pytest.raises(StoreError, match="^event_conflict$"):
        store.reconcile(claim.run.run_id, claim.run.version, "absent", event_id=event_id)
    final = store.reconcile(unknown.run_id, unknown.version, "absent")
    assert final.status == "outcome_unknown"
    assert store.expired() == []
    with pytest.raises(StoreError, match="^version_conflict$"):
        finish(store, claim)
    clock[0] += 31 * 86400
    assert store.prune(apply=True) == []
    assert store.detail(final.run_id).run == final


def test_prune_only_old_confirmed_report_with_cascade(store: RunStore, clock: list[float]):
    done = finish(store, claimed(store))
    unknown_claim = claimed(store)
    unknown_report = report_for(unknown_claim)
    unknown_report.mcp.adapter_outcome = "outcome_unknown"
    unknown = finish(store, unknown_claim, status="outcome_unknown", report=unknown_report)
    live = claimed(store)
    queued_run = queued(store)
    risk_claim = claimed(store)
    risk_report = report_for(risk_claim)
    risk_report.execution.cleanup = "unconfirmed"
    risk = finish(
        store,
        risk_claim,
        status="outcome_unknown",
        report=risk_report,
        executor_state="unavailable",
    )
    clock[0] += 30 * 86400
    assert store.prune() == []
    clock[0] += 1
    assert set(store.prune()) == {done.run_id, unknown.run_id}
    assert len(store.list_runs()) == 5
    assert set(store.prune(apply=True)) == {done.run_id, unknown.run_id}
    assert {r.run_id for r in store.list_runs()} == {
        live.run.run_id,
        queued_run.run_id,
        risk.run_id,
    }
    assert sql(store, "SELECT count(*) FROM events") == [(6,)]
    assert sql(store, "SELECT count(*) FROM artifacts") == [(1,)]
    assert sql(store, "SELECT count(*) FROM attempts") == [(2,)]


@pytest.mark.parametrize(
    "method,args,code",
    [
        ("detail", ("../SECRET",), "invalid_id"),
        ("list_runs", (0,), "invalid_limit"),
        ("list_runs", (101,), "invalid_limit"),
        ("prune", (0,), "invalid_retention"),
        ("claim", (str(uuid4()), 1, 120.0), "invalid_lease"),
    ],
)
def test_fixed_input_errors(store: RunStore, method: str, args: tuple, code: str):
    with pytest.raises(StoreError, match=f"^{code}$"):
        getattr(store, method)(*args)


def test_real_commit_failure_rolls_back_every_part(store: RunStore):
    claim = claimed(store)
    # Deferred FK is legal during statements but fails at COMMIT itself.
    sql(
        store,
        "CREATE TABLE commit_guard (run_id TEXT REFERENCES runs(run_id) "
        "DEFERRABLE INITIALLY DEFERRED)",
    )
    sql(
        store,
        "CREATE TRIGGER fail_commit AFTER INSERT ON artifacts BEGIN "
        "INSERT INTO commit_guard VALUES ('missing'); END",
    )
    with pytest.raises(StoreError, match="^store_unavailable$"):
        finish(store, claim)
    assert store.detail(claim.run.run_id).run == claim.run
    assert len(store.detail(claim.run.run_id).events) == 2
    assert sql(store, "SELECT count(*) FROM artifacts") == [(0,)]
    assert sql(store, "SELECT count(*) FROM commit_guard") == [(0,)]


def test_real_sqlite_full_preserves_running_state(store: RunStore):
    from sqlalchemy import event

    claim = claimed(store)
    page_count = sql(store, "PRAGMA page_count")[0][0]

    def limit_pages(connection, _):
        connection.execute(f"PRAGMA max_page_count={page_count}")

    event.listen(store._database(), "connect", limit_pages)
    report = report_for(claim)
    report.mcp.invocation_id = "synthetic" * 20000
    try:
        with pytest.raises(StoreError, match="^store_unavailable$"):
            finish(store, claim, report=report)
    finally:
        event.remove(store._database(), "connect", limit_pages)
    assert store.detail(claim.run.run_id).run == claim.run
    assert len(store.detail(claim.run.run_id).events) == 2
    assert sql(store, "SELECT count(*) FROM artifacts") == [(0,)]


def test_live_wal_backup_refused_downgrade_and_restore(store: RunStore, tmp_path: Path):
    with sqlite3.connect(store.path) as source:
        source.execute("SELECT count(*) FROM runs").fetchone()
        run = finish(store, claimed(store))
        expected = store.detail(run.run_id)
        expected_report = store.report(run.run_id)
        wal = Path(str(store.path) + "-wal")
        assert wal.exists() and wal.stat().st_size > 0
        backup_path = tmp_path / "backup.sqlite3"
        with sqlite3.connect(backup_path) as backup:
            # SQLite backup includes a committed WAL snapshot; do not copy the main file alone.
            source.backup(backup)
        with pytest.raises(StoreError, match="^migration_not_empty$"):
            store.downgrade_empty()
        assert store.detail(run.run_id) == expected
        # A later source write must not appear in the restored backup snapshot.
        queued(store)
        restore_dir = tmp_path / "restored"
        restore_dir.mkdir(mode=0o700)
        with sqlite3.connect(backup_path) as backup:
            with sqlite3.connect(restore_dir / "state.sqlite3") as destination:
                backup.backup(destination)
    restored = RunStore(restore_dir)
    restored.initialize()
    assert restored.list_runs() == [run]
    assert restored.detail(run.run_id) == expected
    assert restored.report(run.run_id) == expected_report
    assert (
        digest(canonical(restored.report(run.run_id).model_dump(mode="json"))) == run.report_sha256
    )
    restored.close()
