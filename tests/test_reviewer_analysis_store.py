"""Independent persistence probes using synthetic local state only."""

import multiprocessing
import os
import signal
import sqlite3
from pathlib import Path

import pytest
from alembic import command

from agent_workbench.analysis_store.fencing import AnalysisFence
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.store import RunStore
from tests.test_analysis_store import context, started  # noqa: F401
from tests.test_run_store import finish


def hold_owner(directory, task_id, ready):
    with AnalysisFence(Path(directory), task_id):
        ready.set()
        signal.pause()


def test_paused_owner_cannot_be_reconciled_and_killed_owner_keeps_reservation(context, monkeypatch):  # noqa: F811
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    store, fence, _ = context
    pending, _ = started(context)
    task_id = pending.summary.task_id
    fence.close()
    spawn = multiprocessing.get_context("spawn")
    ready = spawn.Event()
    owner = spawn.Process(target=hold_owner, args=(str(store.directory), task_id, ready))
    owner.start()
    try:
        assert ready.wait(10)
        os.kill(owner.pid, signal.SIGSTOP)
        with pytest.raises(StoreError, match="^analysis_busy$"):
            store.reconcile(task_id, pending.summary.summary_revision, pending.sha256)
        assert store.get(task_id).sha256 == pending.sha256
        owner.kill()
        owner.join(5)
        assert owner.exitcode == -signal.SIGKILL
        recovered = store.reconcile(task_id, pending.summary.summary_revision, pending.sha256)
        assert recovered.summary.state.outcome == "outcome_unknown"
        assert recovered.summary.usage == pending.summary.usage
        assert recovered.summary.usage.reserved_tokens == 150
    finally:
        if owner.is_alive():
            owner.kill()
            owner.join(5)


def test_v2_full_report_and_run_rows_survive_v3_upgrade(tmp_path):
    store = RunStore(tmp_path / "state")
    store.initialize()
    run = store.create("isolated-fixture", "pass", "a" * 64, "b" * 64)
    claim = store.claim(run.run_id, run.version)
    finish(store, claim)
    expected = store.report(run.run_id)
    with store._transaction(write=True) as connection:
        connection.exec_driver_sql(
            "INSERT INTO web_requests VALUES (?, ?, 0, 0)", (run.run_id, "c" * 64)
        )
        command.downgrade(store._migration(connection), "0002_web_requests")
    names = ("runs", "attempts", "events", "artifacts", "web_requests")
    with sqlite3.connect(store.path) as database, sqlite3.connect(tmp_path / "backup") as backup:
        database.backup(backup)
        before = {
            name: database.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall() for name in names
        }
    with pytest.raises(StoreError, match="^schema_incompatible$"):
        store.report(run.run_id)
    store.initialize()
    with sqlite3.connect(store.path) as database:
        assert {
            name: database.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall() for name in names
        } == before
    assert store.report(run.run_id) == expected
    with pytest.raises(StoreError, match="^migration_not_empty$"):
        store.downgrade_empty()
    store.close()
