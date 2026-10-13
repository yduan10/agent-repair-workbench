"""Independent first-batch probes; no Docker or API execution."""

import multiprocessing
import os
import signal
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command

from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Report
from agent_workbench.run_store.models import StoreError
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from agent_workbench.web_runs.fencing import OwnerFence
from agent_workbench.web_runs.models import ReproductionRequest
from agent_workbench.web_runs.store import WebRunStore


def held_owner(directory, sender):
    with OwnerFence(Path(directory)):
        sender.send("locked")
        signal.pause()


def test_real_sigstop_owner_blocks_and_sigkill_releases(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    directory = tmp_path / "state"
    store = WebRunStore(directory)
    store.initialize()
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    child = ctx.Process(target=held_owner, args=(str(directory), sender))
    child.start()
    try:
        assert receiver.poll(10) and receiver.recv() == "locked"
        os.kill(child.pid, signal.SIGSTOP)
        _, status = os.waitpid(child.pid, os.WUNTRACED)
        assert os.WIFSTOPPED(status)
        with pytest.raises(StoreError, match="^runner_busy$"):
            OwnerFence(directory).acquire()
        os.kill(child.pid, signal.SIGKILL)
        child.join(10)
        assert child.exitcode == -signal.SIGKILL
        with OwnerFence(directory):
            pass
    finally:
        if child.is_alive():
            child.kill()
        child.join(10)
        store.close()


def test_v1_completed_report_upgrade_preserves_all_bytes(tmp_path):
    store = WebRunStore(tmp_path / "state")
    store.initialize()
    run = store.create("isolated-fixture", "pass", "a" * 64, "b" * 64)
    claim = store.claim(run.run_id, run.version)
    report = SandboxReport(
        run_id=claim.run.attempt_id,
        record_id=run.run_id,
        mcp=MCPReport(
            invocation_id="synthetic",
            adapter_outcome="completed",
            contract_report=Report(status="passed"),
        ),
        execution=ExecutionEvidence(cleanup="removed"),
    )
    finished = store.finish(
        run.run_id,
        claim.run.attempt_id,
        claim.token,
        claim.run.version,
        "succeeded",
        report,
        "absent",
    )
    detail = store.detail(run.run_id)
    with store._transaction(write=True) as connection:
        command.downgrade(store._migration(connection), "0001_run_store")

    def snapshot():
        with sqlite3.connect(store.path) as connection:
            return {
                name: connection.execute(f"SELECT * FROM {name}").fetchall()
                for name in ("runs", "attempts", "events", "artifacts")
            }

    before = snapshot()
    with pytest.raises(StoreError, match="^schema_incompatible$"):
        store.detail(run.run_id)
    store.initialize()
    assert snapshot() == before
    assert store.detail(run.run_id) == detail
    assert store.report(run.run_id) == report
    assert store.detail(run.run_id).run.report_sha256 == finished.report_sha256
    with OwnerFence(store.directory) as fence:
        new = store.admit(ReproductionRequest(request_id=str(uuid4()), scenario="pass"), fence)
        assert new.run.status == "running"
    store.close()
