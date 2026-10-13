"""Opt-in real-container gate. Never pull/build images or touch unrelated containers."""

import json
import os
import signal
import subprocess
import sys
import time

import anyio
import pytest

from agent_workbench.mcp_config import canonical
from agent_workbench.runner.docker import DockerControl
from agent_workbench.runner.service import run_sandbox

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("AWB_DOCKER_TESTS") != "1", reason="explicit Docker gate disabled"
    ),
]
CASE = canonical({"case_id": "container-test", "tool": "lookup", "arguments": {"id": 7}})


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("pass", 0),
        ("policy_probe", 0),
        ("tool_error", 1),
        ("timeout", 2),
        ("response_lost", 2),
        ("duplicate_result", 2),
        ("crash_before_call", 2),
        ("crash_during_call", 2),
        ("crash_before_result", 2),
        ("stdout_flood", 2),
        ("stdout_total_flood", 2),
        ("stderr_flood", 2),
        ("spawn_child", 2),
        ("oom", 2),
        ("cpu_spin", 2),
        ("pid_limit", 2),
    ],
)
async def test_real_fault_matrix(scenario, expected, monkeypatch):
    monkeypatch.setenv("AWB_TEST_SECRET", "SYNTHETIC_SECRET_MUST_NOT_REACH_CONTAINER")
    observed = {}
    original = DockerControl.cleanup

    async def cleanup(self, run_id):
        name = "awb-p003-" + run_id
        inspected = await self.inspect(name)
        if (
            inspected
            and inspected["State"]["Running"]
            and scenario
            in ("pass", "policy_probe", "response_lost", "spawn_child", "cpu_spin", "pid_limit")
        ):
            observed["calls"] = await self.command("exec", name, "cat", "/tmp/call-count")
            if scenario == "spawn_child":
                observed["child"] = await self.command("exec", name, "cat", "/tmp/child-pid")
            if scenario == "pid_limit":
                observed["pids"] = await self.command("exec", name, "cat", "/tmp/pid-limit")
        return await original(self, run_id)

    monkeypatch.setattr(DockerControl, "cleanup", cleanup)
    report = await run_sandbox(canonical({"scenario": scenario}), CASE, stage_timeout=2)
    assert report.exit_code() == expected, report.model_dump_json()
    assert report.execution.cleanup == "removed", report.model_dump_json()
    assert await (await DockerControl.connect()).inspect("awb-p003-" + report.run_id) is None
    assert "SYNTHETIC_SECRET" not in report.model_dump_json()
    if scenario in (
        "pass",
        "policy_probe",
        "response_lost",
        "spawn_child",
        "cpu_spin",
        "pid_limit",
    ):
        assert observed["calls"].strip() == b"1"  # real side effect; never retried
    if scenario == "spawn_child":
        assert int(observed["child"]) > 1
    if scenario == "pid_limit":
        assert observed["pids"].strip() == b"11"  # EAGAIN from actual cgroup quota
    if scenario in (
        "timeout",
        "response_lost",
        "spawn_child",
        "cpu_spin",
        "pid_limit",
        "crash_during_call",
        "crash_before_result",
        "oom",
    ):
        assert report.mcp.adapter_outcome == "outcome_unknown"
    if scenario == "crash_before_call":
        assert report.mcp.adapter_outcome == "transport_error"
    if scenario == "tool_error":
        assert report.mcp.adapter_outcome == "tool_error"
    expected_errors = {
        "stdout_flood": "frame_limit_exceeded",
        "stdout_total_flood": "stdout_limit_exceeded",
        "stderr_flood": "stderr_limit_exceeded",
        "duplicate_result": "duplicate_response_id",
    }
    if scenario in expected_errors:
        assert report.execution.error == expected_errors[scenario]
    if scenario == "oom":
        assert report.execution.oom_killed or report.execution.container_exit_code == 137


@pytest.mark.anyio
@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGKILL])
async def test_host_death_and_watchdog(tmp_path, signum):
    control = await DockerControl.connect()
    # A fresh UUID emitted by this test's wrapper identifies only its own execution.
    identity = tmp_path / "identity"
    script = tmp_path / "host.py"
    script.write_text("""import sys
from pathlib import Path
from agent_workbench.runner.docker import DockerControl
from agent_workbench.runner.cli import check
original = DockerControl.create
async def create(self, run_id, *args):
    Path(sys.argv[3]).write_text(run_id)
    return await original(self, run_id, *args)
DockerControl.create = create
if __name__ == "__main__":
    raise SystemExit(check(Path(sys.argv[1]), Path(sys.argv[2])))
""")
    config, case = tmp_path / "config.json", tmp_path / "case.json"
    config.write_bytes(canonical({"scenario": "spawn_child", "lifetime": 8}))
    case.write_bytes(CASE)
    process = subprocess.Popen(
        [sys.executable, str(script), str(config), str(case), str(identity)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "AWB_STATE_DIR": str(tmp_path / "state")},
    )
    run_id = None
    try:
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if identity.exists():
                run_id = identity.read_text()
                info = await control.inspect("awb-p003-" + run_id)
                if info and info["State"]["Running"]:
                    try:
                        child = await control.command("exec", info["Id"], "cat", "/tmp/child-pid")
                    except Exception:
                        child = b""
                    if child:
                        break
            await anyio.sleep(0.1)
        else:
            pytest.fail("test container did not reach child-spawn phase")
        assert await control.reap(run_id, False) == "running"
        assert await control.reap(run_id, True) == "running"
        os.kill(process.pid, signum)  # exclusively this test's host process
        output, errors = await anyio.to_thread.run_sync(lambda: process.communicate(timeout=15))
        assert errors == b""
        if signum == signal.SIGTERM:
            report = json.loads(output)
            assert report["execution"]["cleanup"] == "removed"
            assert report["mcp"]["adapter_outcome"] == "outcome_unknown"
            assert process.returncode == 2
            assert await control.inspect("awb-p003-" + run_id) is None
        else:
            assert process.returncode == -signal.SIGKILL
            with anyio.fail_after(12):
                while True:
                    info = await control.inspect("awb-p003-" + run_id)
                    if info and not info["State"]["Running"]:
                        break
                    await anyio.sleep(0.2)
            assert info["State"]["ExitCode"] == 124
            assert info["State"]["Pid"] == 0
            assert await control.reap(run_id, False) == "stopped"
            assert await control.reap(run_id, True) == "removed"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=15)
        if run_id:
            await control.cleanup(run_id)
