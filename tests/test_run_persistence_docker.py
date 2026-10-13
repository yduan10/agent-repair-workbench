"""P0-04 opt-in actual Docker + subprocess + SQLite recovery gate."""

import json
import os
import signal
import subprocess
import sys

import anyio
import pytest

from agent_workbench.mcp_config import canonical
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.docker import DockerControl, DockerFailure

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(os.environ.get("AWB_DOCKER_TESTS") != "1", reason="Docker gate disabled"),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.parametrize(
    "scenario,expected,status", [("pass", 0, "succeeded"), ("response_lost", 2, "outcome_unknown")]
)
def test_real_cli_run_survives_independent_read_process(tmp_path, scenario, expected, status):
    config, case = tmp_path / "config.json", tmp_path / "case.json"
    config.write_bytes(canonical({"scenario": scenario}))
    case.write_bytes(canonical({"case_id": "p004-real", "tool": "lookup", "arguments": {"id": 7}}))
    env = {**os.environ, "AWB_STATE_DIR": str(tmp_path / "state")}
    command = [sys.executable, "-m", "agent_workbench"]
    run = subprocess.run(
        command + ["sandbox-check", "--server-config", str(config), "--case", str(case)],
        capture_output=True,
        env=env,
        timeout=55,
    )
    assert run.returncode == expected and run.stderr == b"", run.stdout
    report = json.loads(run.stdout)
    detail = subprocess.run(
        command + ["runs", "show", report["record_id"]], capture_output=True, env=env, timeout=5
    )
    assert detail.returncode == 0 and detail.stderr == b""
    data = json.loads(detail.stdout)
    assert data["run"]["status"] == status
    assert data["run"]["attempt_id"] == report["run_id"]
    assert [event["kind"] for event in data["events"]] == ["created", "claimed", "finished"]
    saved = subprocess.run(
        command + ["runs", "report", report["record_id"]], capture_output=True, env=env, timeout=5
    )
    assert json.loads(saved.stdout) == report


@pytest.mark.anyio
async def test_sigkill_restart_reconciles_without_replaying_effect(tmp_path):
    state = tmp_path / "state"
    env = {**os.environ, "AWB_STATE_DIR": str(state)}
    script = tmp_path / "worker.py"
    script.write_text("""import anyio
from functools import partial
from agent_workbench.mcp_config import canonical
from agent_workbench.run_store.execution import execute_saved
if __name__ == "__main__":
    anyio.run(partial(execute_saved,
        canonical({"scenario": "spawn_child", "lifetime": 8}),
        canonical({"case_id": "kill-recovery", "tool": "lookup", "arguments": {"id": 7}}),
        lease_seconds=5))
""")
    process = subprocess.Popen(
        [sys.executable, str(script)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    control = await DockerControl.connect()
    store = RunStore(state)
    attempt = None
    try:
        with anyio.fail_after(8):
            while True:
                rows = store.list_runs()
                if rows and rows[0].attempt_id:
                    run = rows[0]
                    attempt = run.attempt_id
                    try:
                        count = await control.command(
                            "exec", "awb-p003-" + attempt, "cat", "/tmp/call-count"
                        )
                        if count.strip() == b"1":
                            break
                    except DockerFailure:
                        pass
                await anyio.sleep(0.05)
        assert store.detail(run.run_id).run.status == "running"
        os.kill(process.pid, signal.SIGKILL)
        stdout, stderr = await anyio.to_thread.run_sync(lambda: process.communicate(timeout=3))
        assert process.returncode == -signal.SIGKILL and stdout == stderr == b""
        with anyio.fail_after(12):
            while True:
                info = await control.inspect("awb-p003-" + attempt)
                if info and info["State"]["Running"] is False:
                    break
                await anyio.sleep(0.2)
        restart = await anyio.to_thread.run_sync(
            lambda: subprocess.run(
                [sys.executable, "-m", "agent_workbench", "runs", "reconcile"],
                env=env,
                capture_output=True,
                timeout=10,
            )
        )
        assert restart.returncode == 0 and restart.stderr == b""
        updated = json.loads(restart.stdout)["runs"]
        assert len(updated) == 1 and updated[0]["status"] == "outcome_unknown"
        assert updated[0]["executor_state"] == "stopped" and updated[0]["attempt_id"] == attempt
        detail = store.detail(run.run_id)
        assert [event.kind for event in detail.events] == ["created", "claimed", "reconciled"]
        assert detail.run.report_sha256 is None
        assert store.prune(days=1, apply=True) == []
        assert await control.reap(attempt, True) == "removed"
    finally:
        if process.poll() is None:
            process.kill()
            await anyio.to_thread.run_sync(lambda: process.communicate(timeout=3))
        if attempt:
            await control.cleanup(attempt)
        store.close()
