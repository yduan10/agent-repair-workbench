"""Independent CLI boundary probes, with no real model or container invocation."""

import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest

from agent_workbench.cli import main
from agent_workbench.repair_runtime import cli
from tests.agents.test_repair_cli import configured as configured
from tests.agents.test_repair_tool_bridge import ctx as ctx


def test_symlink_snapshot_root_cannot_write_outside_state(ctx, configured, tmp_path, capsys):
    outside = tmp_path / "outside"
    outside.mkdir()
    (ctx.store.directory / "repair-snapshots").symlink_to(outside, target_is_directory=True)
    assert main(["repair"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "AUDITED_RESOURCE_UNAVAILABLE"
    assert configured[0].calls == 0 and not ctx.attempts
    assert list(outside.iterdir()) == []


def test_cli_tighter_model_budget_is_the_same_durable_budget(ctx, configured, capsys):
    assert main(["repair", "--model-calls", "1"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["task"]["budget"]["model_calls"] == 1
    assert result["task"]["usage"]["model_calls"] == 1
    assert result["task"]["outcome"] == "budget_exceeded"
    assert configured[0].calls == 1 and len(ctx.attempts) == 1


@pytest.mark.parametrize("flag", ["cancelled", "requires_reconcile"])
def test_verified_task_with_incomplete_runtime_flag_never_exits_success(
    ctx, configured, monkeypatch, capsys, flag
):
    original = cli.RepairController.run

    async def marked(self):
        result = await original(self)
        return replace(result, **{flag: True})

    monkeypatch.setattr(cli.RepairController, "run", marked)
    assert main(["repair"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["task"]["outcome"] == "candidate_verified" and result[flag]
    assert "claim" not in result and "claim_sha256" not in json.dumps(result)


def test_sigint_during_model_produces_recoverable_json_and_exit_two(ctx, configured):
    script = r"""
import asyncio, os, signal, sys
from pathlib import Path
from agent_workbench.cli import main
from agent_workbench.repair_runtime import cli
from agent_workbench.model_gateway.gateway import PreparedCall
from agent_workbench.mcp_config import canonical,digest
class Adapter:
    config_sha256 = "a" * 64
    def prompt(self,role): return "synthetic signal test"
    def prepare(self,role,messages,output_cap):
        raw=canonical(messages)
        return PreparedCall(raw,digest(raw),10000,output_cap,"c"*64)
    async def send(self,prepared,timeout):
        asyncio.get_running_loop().call_soon(os.kill,os.getpid(),signal.SIGINT)
        await asyncio.sleep(30)
cli.ROOT=Path(sys.argv[1])
cli.RepairDeepSeekAdapter=lambda config: Adapter()
sys.exit(main(["repair"]))
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(ctx.image)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == 2, process.stderr
    result = json.loads(process.stdout)
    assert result["cancelled"]
    assert result["task"]["outcome"] == "outcome_unknown"
    assert result["task"]["usage"]["reserved_tokens"] == 18192
    assert ctx.store.get(result["task"]["task_id"]).task_sha256 == result["sha256"]
    assert "synthetic-secret" not in process.stdout + process.stderr
    assert "Traceback" not in process.stderr
