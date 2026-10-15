"""CLI boundary: local regular files, bounded worker, safe JSON-only output."""

import argparse
import math
import multiprocessing as mp
import os
import stat
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import NoReturn

from agent_workbench.checker import MAX_BYTES, check_bytes
from agent_workbench.models import Report, incomplete


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse normally echoes invalid arguments, which may contain secrets.
        self.exit(2, "invalid_arguments\n")


def _read(path: Path) -> bytes:
    # O_NONBLOCK prevents a FIFO swap between lookup/open from blocking the parent.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("regular file required")
        if info.st_size > MAX_BYTES:
            return b" " * (MAX_BYTES + 1)
        with os.fdopen(fd, "rb", closefd=False) as source:
            return source.read(MAX_BYTES + 1)
    finally:
        os.close(fd)


def _worker(raw: bytes, channel: Connection) -> None:
    try:
        channel.send_bytes(check_bytes(raw).model_dump_json().encode("utf-8"))
    except Exception:
        # Transport or resource failure must be observed by the parent, not logged.
        pass
    finally:
        channel.close()


def run_check(raw: bytes, timeout: float) -> Report:
    """Spawn a pure checker; a timeout or crashed worker can never pass a run."""
    if not math.isfinite(timeout) or not 0.1 <= timeout <= 30:
        return incomplete("invalid_document")
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(raw, sender), daemon=True)
    deadline = time.monotonic() + timeout
    started = False
    try:
        process.start()
        started = True
        sender.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not receiver.poll(remaining):
            return incomplete("check_timeout")
        payload = receiver.recv_bytes(MAX_BYTES)
        report = Report.model_validate_json(payload)
        remaining = max(0.0, deadline - time.monotonic())
        process.join(remaining)
        if process.is_alive():
            return incomplete("check_timeout")
        if process.exitcode != 0:
            return incomplete("checker_error")
        return report
    except (EOFError, OSError, ValueError, RuntimeError):
        return incomplete("checker_error")
    finally:
        sender.close()
        receiver.close()
        if started:
            if process.is_alive():
                process.terminate()
                process.join(0.2)
            if process.is_alive():
                process.kill()
                process.join(0.2)
            if not process.is_alive():
                process.close()


def _timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a number") from None
    if not math.isfinite(parsed) or not 0.1 <= parsed <= 30:
        raise argparse.ArgumentTypeError("timeout must be between 0.1 and 30 seconds")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="agent-workbench")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check a local tool-call evidence JSON")
    check.add_argument("path", type=Path)
    check.add_argument("--timeout", type=_timeout, default=5.0)
    mcp = commands.add_parser("mcp-check", help="call a reviewed local MCP profile and check it")
    mcp.add_argument("--server-config", type=Path, required=True)
    mcp.add_argument("--case", type=Path, required=True)
    sandbox = commands.add_parser("sandbox-check", help="run the reviewed isolated fixture")
    sandbox.add_argument("--server-config", type=Path, required=True)
    sandbox.add_argument("--case", type=Path, required=True)
    reap = commands.add_parser("sandbox-reap", help="inspect or remove one stopped owned container")
    reap.add_argument("--run-id", required=True)
    reap.add_argument("--apply", action="store_true")
    from agent_workbench.run_store.cli import configure as configure_runs

    configure_runs(commands.add_parser("runs", help="inspect durable local execution records"))
    from agent_workbench.orchestration.cli import configure, configure_history

    configure(commands.add_parser("analyze", help="analyze a reviewed case with bounded roles"))
    configure_history(commands.add_parser("analyses", help="read or reconcile analyses"))
    from agent_workbench.repair_runtime.cli import configure as configure_repair

    configure_repair(commands.add_parser("repair", help="repair the fixed audited MCP fixture"))
    from agent_workbench.repair_recovery.cli import configure as configure_recovery

    configure_recovery(
        commands.add_parser(
            "repair-recovery", help="inspect or explicitly reap orphan repair executions"
        )
    )
    args = parser.parse_args(argv)
    if args.command == "repair-recovery":
        from agent_workbench.repair_recovery.cli import main as recovery_main

        return recovery_main(args)
    if args.command == "repair":
        from agent_workbench.repair_runtime.cli import main as repair_main

        return repair_main(args)
    if args.command in ("analyze", "analyses"):
        from agent_workbench.orchestration.cli import main as analyses_main

        return analyses_main(args)
    if args.command == "runs":
        from agent_workbench.run_store.cli import main as runs_main

        return runs_main(args)
    if args.command == "sandbox-check":
        from agent_workbench.runner.cli import check as sandbox_check

        return sandbox_check(args.server_config, args.case)
    if args.command == "sandbox-reap":
        from agent_workbench.runner.cli import reap as sandbox_reap

        return sandbox_reap(args.run_id, args.apply)
    if args.command == "mcp-check":
        from agent_workbench.mcp_cli import main as mcp_main

        return mcp_main(args.server_config, args.case)
    try:
        raw = _read(args.path)
        report = (
            incomplete("input_limit_exceeded")
            if len(raw) > MAX_BYTES
            else run_check(raw, args.timeout)
        )
    except OSError:
        report = incomplete("input_unreadable")
    except KeyboardInterrupt:
        report = incomplete("checker_error")
    print(report.model_dump_json())
    return {"passed": 0, "failed": 1, "inconclusive": 2}[report.status]
