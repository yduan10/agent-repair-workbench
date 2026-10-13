"""Real stdio integration: the checker, SDK and child process all execute."""

import os
import subprocess
import sys
import time
from functools import partial

import anyio
import pytest
from mcp.client import stdio

from agent_workbench.mcp_adapter import run_mcp
from agent_workbench.mcp_config import CallCase, ServerConfig, canonical
from agent_workbench.mcp_models import MCPReport

CASE = canonical({"case_id": "synthetic", "tool": "lookup", "arguments": {"id": 1}})


def execute(tmp_path, scenario="pass", case=CASE, **limits):
    with (tmp_path / "fixture-stderr.txt").open("w+") as log:
        report = anyio.run(
            partial(
                run_mcp,
                canonical({"profile": "contract-fixture", "scenario": scenario}),
                case,
                errlog=log,
                **limits,
            )
        )
        log.seek(0)
        calls = log.read().splitlines().count("fixture_call")
    return report, calls


@pytest.mark.parametrize(
    ("scenario", "outcome", "status", "code", "calls"),
    [
        ("pass", "completed", "passed", None, 1),
        ("wrong_type", "completed", "failed", "output_schema_violation", 1),
        ("missing_content", "completed", "failed", "structured_content_missing", 1),
        ("null_content", "completed", "failed", "output_schema_violation", 1),
        ("no_output_schema", "completed", "passed", None, 1),
        ("tool_error", "tool_error", "failed", "tool_error", 1),
        ("paginated", "completed", "passed", None, 1),
        ("cursor_loop", "unsupported", None, "pagination_cycle", 0),
        ("duplicate_tools", "unsupported", None, "duplicate_tool_name", 0),
        ("protocol_error", "protocol_error", None, "protocol_error", 1),
        ("crash", "outcome_unknown", None, "call_interrupted", 1),
        ("unsupported_schema", "unsupported", None, "unsupported_schema", 0),
        ("invalid_schema", "unsupported", None, "invalid_schema", 0),
        ("unexpected_protocol", "unsupported", None, "unsupported_protocol", 0),
    ],
)
def test_real_stdio_scenarios(tmp_path, scenario, outcome, status, code, calls):
    report, observed = execute(tmp_path, scenario)
    assert report.adapter_outcome == outcome, report
    assert observed == calls
    contract = report.contract_report
    assert (contract.status if contract else None) == status
    findings = contract.findings if contract else report.preflight_findings
    assert code is None or code in [f.code for f in findings]
    assert report.source.kind == "mcp_sdk_normalized"
    assert report.source.wire_json_integrity == "not_checked"
    if scenario == "no_output_schema":
        assert contract.checks.output == "not_checked"
    if scenario == "wrong_type":
        assert contract.findings[0].instance_path == "/result/structured_content/count"
        assert "synthetic_wrong_type" not in report.model_dump_json()


def test_invalid_input_is_never_dispatched(tmp_path):
    raw = canonical({"case_id": "synthetic", "tool": "lookup", "arguments": {"id": "SECRET"}})
    report, calls = execute(tmp_path, case=raw)
    assert report.adapter_outcome == "precheck_rejected"
    assert report.exit_code() == 1
    assert calls == 0
    assert report.contract_report is None
    assert report.preflight_findings[0].code == "input_schema_violation"
    assert "result_missing" not in report.model_dump_json()
    assert "SECRET" not in report.model_dump_json()


def test_unknown_tool_is_not_called(tmp_path):
    raw = canonical({"case_id": "synthetic", "tool": "missing", "arguments": {}})
    report, calls = execute(tmp_path, case=raw)
    assert report.preflight_findings[0].code == "tool_not_found"
    assert calls == 0


@pytest.mark.parametrize("scenario", ["pass", "timeout", "crash"])
def test_real_child_reaped(tmp_path, monkeypatch, scenario):
    pids = []
    original = stdio._create_platform_compatible_process

    async def observed(*args, **kwargs):
        process = await original(*args, **kwargs)
        pids.append(process.pid)
        return process

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", observed)
    started = time.monotonic()
    report, calls = execute(tmp_path, scenario, stage_timeout=1.0, total_timeout=6.0)
    assert time.monotonic() - started < 13
    assert calls == 1
    assert pids
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    if scenario == "timeout":
        assert report.adapter_outcome == "outcome_unknown"
        assert report.exit_code() == 2


@pytest.mark.parametrize(
    "extra",
    [
        {"command": "sh -c SECRET"},
        {"args": ["/tmp/evil.py"]},
        {"cwd": "/tmp"},
        {"env": {"SECRET_KEY": "SECRET"}},
        {"scenario": "unknown"},
        {"profile": "arbitrary"},
    ],
)
def test_untrusted_launch_configuration_rejected(extra, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("rejected config must never launch a process")

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", forbidden)
    config = canonical({"profile": "contract-fixture", **extra})
    report = anyio.run(run_mcp, config, CASE)
    assert report.adapter_outcome == "precheck_rejected"
    assert report.source.server_code_sha256 is None
    assert "SECRET" not in report.model_dump_json()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"id":1,"id":2}',
        b'{"id":9007199254740993.0}',
        b"\xef\xbb\xbf{}",
        b'{"id":NaN}',
        b"[" * 10000,
    ],
)
def test_case_json_is_not_rewritten(raw):
    report = anyio.run(run_mcp, b'{"profile":"contract-fixture"}', raw)
    assert report.exit_code() != 0
    assert report.source.server_code_sha256 is None


def test_cli_real_profiles_and_log_privacy(tmp_path):
    case = tmp_path / "case.json"
    case.write_bytes(CASE)
    for scenario, expected in [("pass", 0), ("wrong_type", 1), ("protocol_error", 2)]:
        config = tmp_path / "server.json"
        config.write_bytes(canonical({"profile": "contract-fixture", "scenario": scenario}))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_workbench",
                "mcp-check",
                "--server-config",
                str(config),
                "--case",
                str(case),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == expected, result.stdout
        assert not result.stderr
        parsed = MCPReport.model_validate_json(result.stdout)
        assert parsed.exit_code() == expected
        assert "fixture_call" not in result.stdout


def test_case_and_config_models_are_strict():
    assert ServerConfig.model_validate({"profile": "contract-fixture"}).scenario == "pass"
    with pytest.raises(ValueError):
        CallCase.model_validate({"case_id": "case", "tool": "lookup", "arguments": []})


@pytest.mark.parametrize(("stage", "total"), [(float("nan"), 20), (1, float("inf")), (0, 20)])
def test_invalid_budget_never_launches(stage, total, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("invalid budget must not launch")

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", forbidden)
    report = anyio.run(
        partial(
            run_mcp,
            b'{"profile":"contract-fixture"}',
            CASE,
            stage_timeout=stage,
            total_timeout=total,
        )
    )
    assert report.preflight_findings[0].code == "invalid_budget"
    assert report.exit_code() == 2


def test_total_deadline_before_dispatch_is_not_a_tool_failure(tmp_path):
    report, calls = execute(tmp_path, total_timeout=0.1)
    assert report.adapter_outcome == "unsupported"
    assert report.preflight_findings[0].code in ("check_budget_exhausted", "check_timeout")
    assert calls == 0


def test_sdk_environment_is_explicit_not_inherited(tmp_path, monkeypatch):
    observed_env = []
    original = stdio._create_platform_compatible_process
    monkeypatch.setenv("HOME", "/PRIVATE_HOME")
    monkeypatch.setenv("SECRET_API_KEY", "NEVER_INHERIT")
    monkeypatch.setenv("PYTHONPATH", "/PRIVATE_MODULES")

    async def observed(*args, **kwargs):
        observed_env.append(kwargs["env"])
        return await original(*args, **kwargs)

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", observed)
    report, calls = execute(tmp_path)
    assert report.exit_code() == 0 and calls == 1
    assert observed_env
    env = observed_env[0]
    assert "SECRET_API_KEY" not in env and "PYTHONPATH" not in env
    assert env["HOME"] != "/PRIVATE_HOME"
    assert env["PATH"] == "/usr/bin:/bin"


def test_cooperative_cancel_reaps_real_child(tmp_path, monkeypatch):
    original = stdio._create_platform_compatible_process
    pids = []

    async def observed(*args, **kwargs):
        process = await original(*args, **kwargs)
        pids.append(process.pid)
        return process

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", observed)

    async def scenario():
        result = None
        with anyio.move_on_after(1.5):
            result = await run_mcp(b'{"profile":"contract-fixture","scenario":"timeout"}', CASE)
        return result

    report = anyio.run(scenario)
    assert report is not None and report.adapter_outcome == "outcome_unknown"
    assert report.preflight_findings[0].code == "run_cancelled"
    for pid in pids:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_raw_content_is_not_parsed_or_fetched(tmp_path):
    report, calls = execute(tmp_path, "missing_content")
    assert calls == 1
    assert report.contract_report.findings[0].code == "structured_content_missing"
    assert report.content_summary[0].kind == "text"
    assert report.content_summary[0].text_characters == len('{"count":1}')
    report, calls = execute(tmp_path, "resource_content")
    assert calls == 1 and report.exit_code() == 0
    assert report.contract_report.checks.output == "not_checked"
    assert report.content_summary[0].kind == "resource_link"
    assert "example.invalid" not in report.model_dump_json()


def test_unchecked_content_still_counts_toward_size_limit(tmp_path):
    report, calls = execute(tmp_path, "oversized_content")
    assert calls == 1
    assert report.adapter_outcome == "completed"
    assert report.contract_report.status == "inconclusive"
    assert report.contract_report.findings[0].code == "input_limit_exceeded"


def test_cancel_during_preflight_never_dispatches(tmp_path, monkeypatch):
    from agent_workbench import mcp_adapter

    original = mcp_adapter._Run.check

    async def scenario():
        entered = anyio.Event()
        report = None

        async def delayed(self, envelope):
            checked = await original(self, envelope)
            if "result" not in envelope:
                entered.set()
                with anyio.CancelScope(shield=True):
                    await anyio.sleep(0.1)
            return checked

        monkeypatch.setattr(mcp_adapter._Run, "check", delayed)
        with (tmp_path / "preflight.log").open("w+") as log:
            async with anyio.create_task_group() as tasks:
                with anyio.CancelScope() as scope:

                    async def cancel():
                        await entered.wait()
                        scope.cancel()

                    tasks.start_soon(cancel)
                    report = await run_mcp(b'{"profile":"contract-fixture"}', CASE, errlog=log)
                tasks.cancel_scope.cancel()
            log.seek(0)
            assert "fixture_call" not in log.read()
        return report

    report = anyio.run(scenario)
    assert report is not None
    assert report.adapter_outcome == "transport_error"
    assert report.exit_code() == 2
