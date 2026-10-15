"""CLI tests never call a provider or Docker; the controller/SQLite are real."""

import json
import sqlite3

import pytest

from agent_workbench.cli import main
from agent_workbench.model_gateway.gateway import PROFILE, Reply
from agent_workbench.repair_runtime import cli
from tests.agents.test_repair_controller import Scripted
from tests.agents.test_repair_tool_bridge import ctx as ctx


@pytest.fixture
def configured(ctx, monkeypatch):
    monkeypatch.setenv("AWB_STATE_DIR", str(ctx.store.directory))
    monkeypatch.setenv("AWB_MODEL_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("AWB_MODEL_NAME", "deepseek-flash")
    monkeypatch.setenv("AWB_MODEL_API_KEY", "synthetic-secret-do-not-print")
    monkeypatch.setenv("AWB_MODEL_LIMIT_PROFILE", PROFILE)
    monkeypatch.setattr(cli, "ROOT", ctx.image)
    adapters = []

    def adapter(config):
        value = Scripted(ctx, ["request_reproduction", "apply_candidate", "compare_candidate"])
        adapters.append(value)
        return value

    monkeypatch.setattr(cli, "RepairDeepSeekAdapter", adapter)
    return adapters


@pytest.mark.parametrize("mode", ["single_role", "three_role"])
def test_cli_real_loop_and_safe_summary(ctx, configured, capsys, mode):
    assert main(["repair", "--mode", mode]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["task"]["outcome"] == "candidate_verified"
    assert result["task"]["mode"] == mode and result["candidate_ids"]
    assert result["task"]["usage"]["model_calls"] == 3
    assert result["task"]["cost_amount"] is None and not result["requires_reconcile"]
    assert ctx.store.get(result["task"]["task_id"]).task_sha256 == result["sha256"]
    for forbidden in ("replacement", "lookup_result", "synthetic-secret", str(ctx.store.directory)):
        assert forbidden not in output


def test_repeated_cli_invocation_creates_new_task_not_resume(ctx, configured, capsys):
    assert main(["repair"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["repair"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first["task"]["task_id"] != second["task"]["task_id"]
    assert first["task"]["baseline"]["snapshot_id"] != second["task"]["baseline"]["snapshot_id"]
    assert len(ctx.attempts) == 10 and len(configured) == 2


def test_missing_config_no_model_or_snapshot(ctx, configured, monkeypatch, capsys):
    monkeypatch.delenv("AWB_MODEL_API_KEY")
    assert main(["repair"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "MODEL_CONFIGURATION_INVALID"}
    assert not configured and not ctx.attempts
    assert not (ctx.store.directory / "repair-snapshots").exists()


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--output-tokens", "8193"),
        ("--model-calls", "13"),
        ("--tool-calls", "21"),
        ("--candidates", "3"),
        ("--timeout", "601"),
        ("--total-tokens", "0"),
    ],
)
def test_budget_invalid_before_any_model(ctx, configured, capsys, flag, value):
    assert main(["repair", flag, value]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "INVALID_CONFIGURATION"}
    assert not configured and not ctx.attempts


def test_old_schema_not_migrated_or_model_called(ctx, configured, capsys):
    with sqlite3.connect(ctx.store._base.path) as db:
        db.execute("UPDATE alembic_version SET version_num='0003_analyses'")
    assert main(["repair"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "STATE_SCHEMA_INCOMPATIBLE"}
    assert configured[0].calls == 0 and not ctx.attempts
    with sqlite3.connect(ctx.store._base.path) as db:
        assert (
            db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003_analyses"
        )
    assert not (ctx.store.directory / "repair-snapshots").exists()


def test_missing_state_not_created(ctx, configured, monkeypatch, capsys, tmp_path):
    absent = tmp_path / "missing-state"
    monkeypatch.setenv("AWB_STATE_DIR", str(absent))
    assert main(["repair"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "STATE_NOT_INITIALIZED"}
    assert configured[0].calls == 0 and not absent.exists()


def test_missing_prepared_image_no_model(ctx, configured, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "ROOT", tmp_path / "missing-image")
    assert main(["repair"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "IMAGE_NOT_PREPARED"}
    assert configured[0].calls == 0 and not ctx.attempts


@pytest.mark.parametrize("reply", [Reply(error="MODEL_USAGE_UNKNOWN"), None])
def test_inconclusive_or_unknown_exit_two_preserves_record(
    ctx, configured, monkeypatch, capsys, reply
):
    adapter = Scripted(ctx, [reply if reply else "needs_evidence"])
    monkeypatch.setattr(cli, "RepairDeepSeekAdapter", lambda config: adapter)
    assert main(["repair"]) == 2
    result = json.loads(capsys.readouterr().out)
    expected = "outcome_unknown" if reply else "inconclusive"
    assert result["task"]["outcome"] == expected and adapter.calls == 1
    stored = ctx.store.get(result["task"]["task_id"])
    assert stored.task.outcome == expected
    if reply:
        assert stored.task.usage.reserved_tokens == 18192


def test_unexpected_error_never_echoes_text(ctx, configured, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic-secret-do-not-print /private/source.py")

    monkeypatch.setattr(cli, "load_repair_case", fail)
    assert main(["repair"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "REPAIR_UNAVAILABLE"}
    assert configured[0].calls == 0


@pytest.mark.parametrize(
    "args",
    [
        ["--task-id", "private-token"],
        ["--case", "/private/file"],
        ["--command", "private-shell"],
        ["--mode", "private-token"],
    ],
)
def test_cli_does_not_expose_resume_or_arbitrary_sources(args, configured, capsys):
    with pytest.raises(SystemExit) as error:
        main(["repair", *args])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.err == "invalid_arguments\n" and not captured.out
    assert not configured


def test_final_read_failure_keeps_recovery_identity(ctx, configured, monkeypatch, capsys):
    from agent_workbench.run_store.models import StoreError

    adapter = Scripted(ctx, ["needs_evidence"])
    monkeypatch.setattr(cli, "RepairDeepSeekAdapter", lambda config: adapter)

    def fail(*args):
        raise StoreError("store_unavailable")

    monkeypatch.setattr(cli.ReproductionStore, "candidates", fail)
    assert main(["repair"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["error"] == "STATE_UNAVAILABLE" and output["requires_reconcile"]
    assert ctx.store.get(output["task_id"]).task_sha256 == output["sha256"]
    assert adapter.calls == 1
