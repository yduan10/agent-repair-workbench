import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from agent_workbench import cli
from agent_workbench.models import Report


def invoke(path, *args):
    return subprocess.run(
        [sys.executable, "-m", "agent_workbench", "check", str(path), *args],
        text=True,
        capture_output=True,
        timeout=15,
    )


@pytest.mark.parametrize(("mutation", "exitcode"), [("valid", 0), ("invalid", 1), ("missing", 2)])
def test_cli_real_process(tmp_path, evidence, mutation, exitcode):
    if mutation == "invalid":
        evidence["call"]["arguments"]["id"] = "secret-cli-value"
    if mutation == "missing":
        del evidence["result"]
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence))
    result = invoke(path)
    assert result.returncode == exitcode, result.stderr
    assert not result.stderr
    assert "secret-cli-value" not in result.stdout
    assert json.loads(result.stdout)["status"] == ["passed", "failed", "inconclusive"][exitcode]


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink", "fifo", "large"])
def test_cli_file_boundaries(tmp_path, kind):
    path = tmp_path / "input"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(tmp_path)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "large":
        path.write_bytes(b" " * (cli.MAX_BYTES + 1))
    result = invoke(path)
    assert result.returncode == 2
    assert not result.stderr
    code = json.loads(result.stdout)["findings"][0]["code"]
    assert code == ("input_limit_exceeded" if kind == "large" else "input_unreadable")


@pytest.mark.parametrize("timeout", ["nan", "inf", "0", "31", "-1", "bad"])
def test_cli_rejects_invalid_timeout(tmp_path, timeout):
    assert invoke(tmp_path, "--timeout", timeout).returncode == 2


def test_cli_usage_error_does_not_echo_values(tmp_path):
    result = invoke(tmp_path, "--unknown=CLI_SECRET")
    assert result.returncode == 2
    assert result.stderr == "invalid_arguments\n"
    assert "CLI_SECRET" not in result.stdout


def hang(raw, channel):
    time.sleep(10)


def crash(raw, channel):
    os._exit(3)


def report_then_crash(raw, channel):
    channel.send_bytes(Report(status="passed").model_dump_json().encode())
    channel.close()
    os._exit(3)


@pytest.mark.parametrize(
    ("target", "code"),
    [(hang, "check_timeout"), (crash, "checker_error"), (report_then_crash, "checker_error")],
)
def test_deadline_crash_and_cleanup(monkeypatch, target, code):
    # Use real processes with controlled failure modes, not mocked success responses.
    context = mp.get_context("fork")
    children = []

    def process(**kwargs):
        kwargs["target"] = target
        child = context.Process(**kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(
        cli.mp, "get_context", lambda _: SimpleNamespace(Pipe=context.Pipe, Process=process)
    )
    before = {p.pid for p in mp.active_children()}
    report = cli.run_check(b"{}", 0.2)
    assert report.status == "inconclusive"
    assert report.findings[0].code == code
    assert {p.pid for p in mp.active_children()} == before
    assert children
