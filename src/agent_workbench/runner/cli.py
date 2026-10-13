"""Local-only P0-03 commands with signal-aware, metadata-only reports."""

import json
import logging
import signal
from pathlib import Path

import anyio

from agent_workbench.cli import _read
from agent_workbench.run_store.execution import execute_saved
from agent_workbench.runner.docker import DockerControl, DockerFailure
from agent_workbench.runner.models import SandboxReport


async def _execute(config: bytes, case: bytes) -> SandboxReport:
    with anyio.CancelScope() as scope:
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        for sig in previous:
            signal.signal(sig, lambda _sig, _frame: scope.cancel())
        try:
            report = await execute_saved(config, case)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return report


def check(config_path: Path, case_path: Path) -> int:
    disabled = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        report = anyio.run(_execute, _read(config_path), _read(case_path))
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt):
        print('{"code":"sandbox_run_unavailable"}')
        return 2
    finally:
        logging.disable(disabled)
    print(report.model_dump_json())
    return report.exit_code()


async def _reap(run_id: str, apply: bool) -> str:
    control = await DockerControl.connect()
    return await control.reap(run_id, apply)


def reap(run_id: str, apply: bool) -> int:
    try:
        status = anyio.run(_reap, run_id, apply)
    except (DockerFailure, ValueError, OSError, RuntimeError, KeyboardInterrupt):
        status = "unconfirmed"
    print(json.dumps({"status": status}))
    return 0 if status in ("absent", "stopped", "removed") else 2
