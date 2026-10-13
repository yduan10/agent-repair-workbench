"""P0-04 orchestration boundary: real SQLite, synthetic execution only where marked."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from agent_workbench.api import create_app
from agent_workbench.cli import main
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Finding, Report
from agent_workbench.run_store import execution
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.schema import artifacts
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.models import SandboxReport

CONFIG = canonical({"scenario": "pass"})
CASE = canonical({"case_id": "synthetic-persistence", "tool": "lookup", "arguments": {"id": 7}})


@pytest.fixture
def anyio_backend():
    return "asyncio"


def successful(attempt_id, record_id=None):
    return SandboxReport(
        run_id=attempt_id,
        record_id=record_id,
        mcp=MCPReport(
            invocation_id=str(uuid4()),
            adapter_outcome="completed",
            contract_report=Report(status="passed"),
        ),
    )


@pytest.mark.parametrize(
    "outcome,contract,cleanup,error,cancelled,status",
    [
        ("completed", "passed", "removed", None, False, "succeeded"),
        ("completed", "failed", "removed", None, False, "failed"),
        ("completed", "inconclusive", "removed", None, False, "outcome_unknown"),
        ("completed", "passed", "unconfirmed", None, False, "outcome_unknown"),
        ("completed", "passed", "removed", "container_failed", False, "outcome_unknown"),
        ("precheck_rejected", None, "not_created", None, False, "failed"),
        ("tool_error", None, "removed", None, False, "failed"),
        ("transport_error", None, "removed", None, True, "cancelled"),
        ("outcome_unknown", None, "removed", None, True, "outcome_unknown"),
        ("transport_error", None, "removed", None, False, "outcome_unknown"),
    ],
)
def test_evidence_drives_terminal_state(outcome, contract, cleanup, error, cancelled, status):
    report = successful(str(uuid4()))
    report.mcp.adapter_outcome = outcome
    report.mcp.contract_report = Report(status=contract) if contract else None
    report.execution.cleanup, report.execution.error = cleanup, error
    if cancelled:
        report.mcp.preflight_findings = [Finding(code="run_cancelled", phase="transport")]
    assert execution.terminal_status(report) == status


@pytest.mark.anyio
async def test_execution_is_claimed_before_effect_and_report_is_atomic(tmp_path, monkeypatch):
    calls = []

    async def perform(config, case, *, run_id):
        other = RunStore(tmp_path)
        try:
            runs = other.list_runs()
            assert len(runs) == 1
            assert runs[0].status == "running" and runs[0].attempt_id == run_id
            assert other.detail(runs[0].run_id).events[-1].kind == "claimed"
            with pytest.raises(StoreError, match="version_conflict"):
                other.claim(runs[0].run_id, 1)
        finally:
            other.close()
        calls.append(run_id)
        return successful(run_id)

    monkeypatch.setattr(execution, "run_sandbox", perform)
    report = await execution.execute_saved(CONFIG, CASE, directory=tmp_path)
    assert report.exit_code() == 0 and len(calls) == 1
    store = RunStore(tmp_path)
    try:
        detail = store.detail(report.record_id)
        assert detail.run.status == "succeeded" and detail.run.version == 3
        assert [event.kind for event in detail.events] == ["created", "claimed", "finished"]
        assert detail.run.report_sha256 == digest(canonical(report.model_dump(mode="json")))
        assert store.report(report.record_id) == report
        raw = (tmp_path / "state.sqlite3").read_bytes()
        assert b"synthetic-persistence" not in raw and b'"arguments"' not in raw
        assert "token" not in detail.model_dump_json()
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["initialize", "claim", "finish"])
async def test_storage_failure_never_replays_and_never_claims_durable_success(
    tmp_path, monkeypatch, phase
):
    calls = []

    async def perform(config, case, *, run_id):
        calls.append(run_id)
        return successful(run_id)

    def fail(*args, **kwargs):
        raise StoreError("store_unavailable")

    monkeypatch.setattr(execution, "run_sandbox", perform)
    monkeypatch.setattr(RunStore, phase, fail)
    report = await execution.execute_saved(CONFIG, CASE, directory=tmp_path)
    assert report.exit_code() == 2
    assert len(calls) == (1 if phase == "finish" else 0)
    if phase == "finish":
        store = RunStore(tmp_path)
        try:
            assert store.detail(report.record_id).run.status == "running"
            with pytest.raises(StoreError, match="report_not_found"):
                store.report(report.record_id)
        finally:
            store.close()


@pytest.mark.anyio
async def test_reconciliation_observes_only_target_no_execution_and_rechecks_unknown(
    tmp_path, monkeypatch
):
    now = [100.0]
    store = RunStore(tmp_path, clock=lambda: now[0])
    store.initialize()
    run = store.create("isolated-fixture", "pass", "0" * 64, "1" * 64)
    claim = store.claim(run.run_id, 1, 2)
    observed = []

    class ReadOnlyDocker:
        async def inspect(self, name):
            observed.append(name)
            raise execution.DockerFailure("docker_unavailable")

    async def connect():
        return ReadOnlyDocker()

    monkeypatch.setattr(execution.DockerControl, "connect", connect)
    assert await execution.reconcile_runs(store) == []
    now[0] = 103.0
    first = await execution.reconcile_runs(store)
    assert first[0].status == "outcome_unknown" and first[0].executor_state == "unavailable"

    async def absent(self, name):
        observed.append(name)
        return None

    monkeypatch.setattr(ReadOnlyDocker, "inspect", absent)
    second = await execution.reconcile_runs(store)
    assert second[0].status == "outcome_unknown" and second[0].executor_state == "absent"
    assert len(observed) == 2 and set(observed) == {"awb-p003-" + claim.run.attempt_id}
    assert await execution.reconcile_runs(store) == []
    now[0] = 99 * 86400.0
    assert store.prune(apply=True) == []  # inspect absence is not saved execution evidence
    assert store.detail(run.run_id).run.status == "outcome_unknown"
    store.close()


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AWB_STATE_DIR", str(tmp_path / "state"))
    store = RunStore(tmp_path / "state")
    yield store
    store.close()


def seed(store):
    store.initialize()
    run = store.create("isolated-fixture", "pass", "0" * 64, "1" * 64)
    claim = store.claim(run.run_id, 1)
    report = successful(claim.run.attempt_id, run.run_id)
    store.finish(run.run_id, claim.run.attempt_id, claim.token, 2, "succeeded", report, "absent")
    return run.run_id, report


def test_read_api_empty_does_not_initialize_and_respects_browser_boundary(local_store):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.get("/api/runs").json() == {"runs": []}
        assert client.get("/api/runs/" + str(uuid4())).status_code == 404
        assert not local_store.path.exists()
        for suffix in ("?limit=101", "?limit=-1", "?limit=1.5", "?limit=" + "7" * 1000):
            assert client.get("/api/runs" + suffix).status_code == 400
        assert client.get("/api/runs/not-a-uuid").status_code == 400
        assert client.get("/api/runs", headers={"origin": "https://evil.test"}).status_code == 403
        assert client.get("/api/runs", headers={"host": "evil.test"}).status_code == 400
        assert client.post("/api/runs").status_code == 405


def test_read_api_round_trip_hash_and_corruption(local_store):
    run_id, report = seed(local_store)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        listing = client.get("/api/runs")
        assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
        row = listing.json()["runs"][0]
        assert row["run_id"] == run_id
        detail = client.get("/api/runs/" + run_id)
        assert len(detail.json()["events"]) == 3
        assert "token" not in detail.text and str(local_store.directory) not in detail.text
        download = client.get(f"/api/runs/{run_id}/report")
        assert download.content == canonical(report.model_dump(mode="json"))
        assert digest(download.content) == row["report_sha256"]
        assert "attachment" in download.headers["content-disposition"]
        with local_store._transaction(write=True) as connection:
            connection.execute(update(artifacts).values(payload=b"SENSITIVE_CORRUPT_BYTES"))
        broken = client.get(f"/api/runs/{run_id}/report")
        assert broken.status_code == 503 and broken.json() == {"error": "report_corrupt"}
        assert "SENSITIVE" not in broken.text


def test_cli_read_reconcile_and_dry_prune(local_store, capsys):
    assert main(["runs", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == {"runs": []}
    assert not local_store.path.exists()
    run_id, report = seed(local_store)
    assert main(["runs", "show", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["run"]["status"] == "succeeded"
    assert main(["runs", "report", run_id]) == 0
    assert json.loads(capsys.readouterr().out) == report.model_dump(mode="json")
    assert main(["runs", "reconcile"]) == 0
    assert json.loads(capsys.readouterr().out) == {"runs": []}
    assert main(["runs", "prune"]) == 0
    assert json.loads(capsys.readouterr().out) == {"apply": False, "run_ids": []}
    assert main(["runs", "prune", "--days", "0"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "invalid_retention"}
