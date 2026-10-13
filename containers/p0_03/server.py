"""P0-03 synthetic MCP stdio fault fixture; run only in the constrained container."""

from __future__ import annotations

import argparse
import errno
import json
import os
import random
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

SCENARIOS = (
    "pass",
    "tool_error",
    "timeout",
    "response_lost",
    "duplicate_result",
    "crash_before_call",
    "crash_during_call",
    "crash_before_result",
    "stdout_flood",
    "stdout_total_flood",
    "pid_limit",
    "stderr_flood",
    "spawn_child",
    "oom",
    "cpu_spin",
    "policy_probe",
)
PROTOCOL = "2025-11-25"
MAX_REQUEST = 65_536


def bounded_int(low: int, high: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError("out_of_range")
        return number

    return parse


def emit(identifier: Any, result: dict[str, Any]) -> None:
    message = {"jsonrpc": "2.0", "id": identifier, "result": result}
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def reject(identifier: Any, code: int) -> None:
    message = {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": "fixture_request_rejected"},
    }
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def output_schema(scenario: str) -> dict[str, Any]:
    properties: dict[str, Any] = {"count": {"type": "integer"}}
    required = ["count"]
    if scenario == "policy_probe":
        properties["policy"] = {
            "type": "object",
            "properties": {
                **{
                    name: {"type": "boolean", "const": True}
                    for name in (
                        "uid_nonzero",
                        "root_write_denied",
                        "only_loopback",
                        "no_host_secret",
                    )
                },
                "cpu_max": {"type": "string", "const": "50000 100000"},
                "memory_max": {"type": "string", "const": "134217728"},
                "pids_max": {"type": "string", "const": "32"},
            },
            "required": [
                "uid_nonzero",
                "root_write_denied",
                "only_loopback",
                "no_host_secret",
                "cpu_max",
                "memory_max",
                "pids_max",
            ],
            "additionalProperties": False,
        }
        required.append("policy")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def policy_probe() -> dict[str, Any]:
    denied = False
    try:
        descriptor = os.open(__file__, os.O_WRONLY)  # owner-writable; no truncation or write
    except OSError as error:
        denied = error.errno == errno.EROFS
    else:
        os.close(descriptor)
    interfaces = {path.name for path in Path("/sys/class/net").iterdir()}
    # Probe only the explicit synthetic marker; never emit environment values.
    return {
        "uid_nonzero": os.getuid() != 0,
        "root_write_denied": denied,
        "only_loopback": interfaces == {"lo"},
        "no_host_secret": "AWB_TEST_SECRET" not in os.environ,
        **{
            name.replace(".", "_"): Path("/sys/fs/cgroup", name).read_text().strip()
            for name in ("cpu.max", "memory.max", "pids.max")
        },
    }


def sleep_forever() -> None:
    while True:
        time.sleep(60)


def side_effect() -> int:
    target = Path("/tmp/call-count")
    count = int(target.read_text()) + 1 if target.exists() else 1
    target.write_text(str(count), encoding="ascii")
    return count


def call(identifier: Any, params: dict[str, Any], args: argparse.Namespace) -> None:
    arguments = params.get("arguments", {})
    if (
        params.get("name") != "lookup"
        or not isinstance(arguments, dict)
        or set(arguments) != {"id"}
        or type(arguments["id"]) is not int
    ):
        reject(identifier, -32602)
        return
    scenario = args.scenario
    if scenario == "crash_during_call":
        os._exit(72)
    count = side_effect()
    if scenario == "crash_before_result":
        os._exit(73)
    if scenario in ("timeout", "response_lost"):
        sleep_forever()
    if scenario in ("stdout_flood", "stdout_total_flood", "stderr_flood"):
        # Fixed synthetic bytes, no supplied argument or environment contents.
        stream = 2 if scenario == "stderr_flood" else 1
        block = b"x" * 4096  # no newline: byte cap must fire before JSON parsing
        if scenario == "stdout_total_flood":
            block = (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/message",
                        "params": {"level": "info", "data": "x" * 32768},
                    }
                )
                + "\n"
            ).encode()
        while True:
            os.write(stream, block)
    if scenario == "spawn_child":
        code = (
            "import os,signal,time; os.setsid(); "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            "open('/tmp/child-pid','w').write(str(os.getpid())); time.sleep(120)"
        )
        subprocess.Popen([sys.executable, "-I", "-B", "-c", code], close_fds=True)
        sleep_forever()
    if scenario == "pid_limit":
        children: list[int] = []
        try:
            while True:
                child_pid = os.fork()  # copy-on-write avoids testing memory instead of PID quota
                if child_pid == 0:
                    sleep_forever()
                    os._exit(0)
                children.append(child_pid)
        except OSError as error:
            Path("/tmp/pid-limit").write_text(str(error.errno), encoding="ascii")
            # Reserve slots for the external synthetic acceptance probe.
            for child_pid in children[-3:]:
                os.kill(child_pid, signal.SIGTERM)
                os.waitpid(child_pid, 0)
            sleep_forever()
    if scenario == "oom":
        blocks = []
        rng = random.Random(args.seed)
        while True:
            blocks.append(bytearray([rng.randrange(256)]) * (8 * 1024 * 1024))
    if scenario == "cpu_spin":
        state = args.seed
        while True:
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
    if scenario == "tool_error":
        emit(
            identifier,
            {"content": [{"type": "text", "text": "synthetic_tool_error"}], "isError": True},
        )
        return
    result: dict[str, Any] = {"count": count}
    if scenario == "policy_probe":
        result["policy"] = policy_probe()
    response = {
        "content": [{"type": "text", "text": json.dumps(result)}],
        "structuredContent": result,
        "isError": False,
    }
    emit(identifier, response)
    if scenario == "duplicate_result":
        emit(identifier, response)


def serve(args: argparse.Namespace) -> int:
    initialized = False
    while True:
        line = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if not line:
            return 0
        if len(line) > MAX_REQUEST or not line.endswith(b"\n"):
            return 65
        try:
            message = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return 65
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return 65
        if "id" not in message:
            continue  # notifications/initialized and other no-response notifications
        identifier = message["id"]
        method = message.get("method")
        if method == "initialize":
            initialized = True
            emit(
                identifier,
                {
                    "protocolVersion": PROTOCOL,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "awb-container-fixture", "version": "1"},
                },
            )
        elif not initialized:
            reject(identifier, -32000)
        elif method == "ping":
            emit(identifier, {})
        elif method == "tools/list":
            if args.scenario == "crash_before_call":
                return 71
            emit(
                identifier,
                {
                    "tools": [
                        {
                            "name": "lookup",
                            "description": "Synthetic container policy/fault fixture",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"id": {"type": "integer"}},
                                "required": ["id"],
                                "additionalProperties": False,
                            },
                            "outputSchema": output_schema(args.scenario),
                        }
                    ]
                },
            )
        elif method == "tools/call" and isinstance(message.get("params"), dict):
            call(identifier, message["params"], args)
        else:
            reject(identifier, -32601)


class FixedErrorParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.exit(2, "invalid_arguments\n")


def main() -> int:
    parser = FixedErrorParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="pass")
    parser.add_argument("--seed", type=bounded_int(0, 2**31 - 1), default=0)
    parser.add_argument("--lifetime", type=bounded_int(5, 45), default=45)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    # The parent runner uses Docker --init: the supervisor is init's direct child.
    # Refuse accidental host execution; this is a guard, not a security boundary.
    if not Path("/.dockerenv").is_file():
        return 64
    if args.worker:
        return serve(args)
    if os.getpid() != 1 and os.getppid() != 1:
        return 64
    deadline = time.monotonic() + args.lifetime
    worker = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            __file__,
            "--worker",
            "--scenario",
            args.scenario,
            "--seed",
            str(args.seed),
            "--lifetime",
            str(args.lifetime),
        ],
        close_fds=True,
    )
    # The supervisor receives cancellation; a runaway worker cannot block this watchdog.
    signal.signal(signal.SIGTERM, lambda *_: os._exit(143))
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    while time.monotonic() < deadline:
        status = worker.poll()
        if status is not None:
            return status if status >= 0 else 128 - status
        time.sleep(0.05)
    os._exit(124)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError):
        # No raw arguments, environment values, or exception text in stderr.
        os._exit(70)
