"""Independent P0-04 synthetic boundary probes; actual SQLite, no Docker side effects."""

from uuid import uuid4

import pytest

from agent_workbench.mcp_config import canonical
from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Finding
from agent_workbench.run_store import execution
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.models import SandboxReport


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("sent,expected", [(False, "cancelled"), (True, "outcome_unknown")])
async def test_cancellation_persists_without_replay(tmp_path, monkeypatch, sent, expected):
    calls = []

    async def perform(config, case, *, run_id):
        calls.append(run_id)
        return SandboxReport(
            run_id=run_id,
            mcp=MCPReport(
                invocation_id=str(uuid4()),
                adapter_outcome="outcome_unknown" if sent else "transport_error",
                preflight_findings=[Finding(code="run_cancelled", phase="transport")],
            ),
        )

    monkeypatch.setattr(execution, "run_sandbox", perform)
    result = await execution.execute_saved(
        canonical({}),
        canonical({"case_id": "test", "tool": "lookup", "arguments": {}}),
        directory=tmp_path,
    )
    store = RunStore(tmp_path)
    try:
        assert store.detail(result.record_id).run.status == expected
        assert store.report(result.record_id) == result
        assert len(calls) == 1 and result.exit_code() == 2
    finally:
        store.close()


@pytest.mark.anyio
@pytest.mark.parametrize("matching,expected", [(False, "mismatch"), (True, "running")])
async def test_reconcile_never_mutates_live_or_mismatched_container(
    tmp_path, monkeypatch, matching, expected
):
    now = [100.0]
    store = RunStore(tmp_path, clock=lambda: now[0])
    store.initialize()
    run = store.create("isolated-fixture", "pass", "0" * 64, "1" * 64)
    claim = store.claim(run.run_id, 1, 1)
    now[0] = 102.0

    class Docker:
        async def inspect(self, name):
            assert name == "awb-p003-" + claim.run.attempt_id
            return {"State": {"Running": True}}

        def _matches(self, item, run_id):
            return matching

        async def cleanup(self, *args):
            pytest.fail("reconciliation must not remove resources")

    async def connect():
        return Docker()

    monkeypatch.setattr(execution.DockerControl, "connect", connect)
    try:
        rows = await execution.reconcile_runs(store)
        assert rows[0].status == "outcome_unknown" and rows[0].executor_state == expected
        assert store.prune(days=1, apply=True) == []
    finally:
        store.close()
