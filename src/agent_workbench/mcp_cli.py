"""CLI-only SDK boundary: no third-party exception or stderr contains raw values."""

import logging
import signal
from pathlib import Path
from uuid import uuid4

import anyio

from agent_workbench.cli import _read
from agent_workbench.mcp_adapter import run_mcp
from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Finding


async def _execute(config: bytes, case: bytes) -> MCPReport:
    # AnyIO cancellation lets stdio_client finish its shielded process cleanup.
    with anyio.CancelScope() as scope:
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        for sig in previous:
            signal.signal(sig, lambda _sig, _frame: scope.cancel())
        try:
            return await run_mcp(config, case)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    # run_mcp converts cooperative cancellation; retain a conservative fallback.
    return MCPReport(
        invocation_id=str(uuid4()),
        adapter_outcome="outcome_unknown",
        preflight_findings=[Finding(code="run_cancelled", phase="adapter")],
    )


def main(config_path: Path, case_path: Path) -> int:
    disabled = logging.root.manager.disable
    # SDK parse/validation logs can include raw values. This standalone CLI
    # emits only our structured report, and restores logging before returning.
    logging.disable(logging.CRITICAL)
    try:
        config, case = _read(config_path), _read(case_path)
        report = anyio.run(_execute, config, case)
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt):
        report = MCPReport(
            invocation_id=str(uuid4()),
            adapter_outcome="unsupported",
            preflight_findings=[Finding(code="mcp_run_unavailable", phase="adapter")],
        )
    finally:
        logging.disable(disabled)
    print(report.model_dump_json())
    return report.exit_code()
