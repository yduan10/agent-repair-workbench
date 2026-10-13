"""P0-03 local Docker control boundary; no raw daemon diagnostics escape."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

import anyio

SCENARIOS = frozenset(
    (
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
)
PROJECT_LABEL = "io.agent-workbench.project"
RUN_LABEL = "io.agent-workbench.run-id"
PROJECT = "p0-03"
TMPFS = "rw,noexec,nosuid,nodev,size=16777216,mode=1777"
ENTRYPOINT = ["python", "-I", "-B", "/opt/fixture/server.py"]
ENV_RULES = {
    "PATH": r"/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": r"C\.UTF-8",
    "GPG_KEY": r"[A-F0-9]{40}",
    "PYTHON_VERSION": r"3\.12\.[0-9]+",
    "PYTHON_SHA256": r"[a-f0-9]{64}",
}


class DockerFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _name(run_id: str) -> str:
    try:
        if str(UUID(run_id)) != run_id:
            raise ValueError
    except (ValueError, AttributeError):
        raise DockerFailure("invalid_run_id") from None
    return "awb-p003-" + run_id


def _full_id(value: str, *, image: bool = False) -> bool:
    return re.fullmatch(r"sha256:[a-f0-9]{64}" if image else r"[a-f0-9]{64}", value) is not None


async def _read(stream: asyncio.StreamReader, limit: int) -> bytes:
    output = bytearray()
    while chunk := await stream.read(8192):
        if len(output) + len(chunk) > limit:
            raise DockerFailure("docker_output_limit")
        output.extend(chunk)
    return bytes(output)


async def _execute(argv: list[str], env: dict[str, str]) -> bytes:
    process: asyncio.subprocess.Process | None = None
    tasks: list[asyncio.Task[bytes]] = []
    try:
        with anyio.fail_after(5):
            process = await asyncio.create_subprocess_exec(
                *argv,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert process.stdout is not None and process.stderr is not None
            tasks = [
                asyncio.create_task(_read(process.stdout, 65_536)),
                asyncio.create_task(_read(process.stderr, 16_384)),
            ]
            stdout, _ = await asyncio.gather(*tasks)
            if await process.wait() != 0:
                raise DockerFailure("docker_command_failed")
            return stdout
    except TimeoutError:
        raise DockerFailure("docker_timeout") from None
    except OSError:
        raise DockerFailure("docker_unavailable") from None
    finally:
        with anyio.CancelScope(shield=True):
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                with anyio.move_on_after(1):
                    await process.wait()


class DockerControl:
    def __init__(self, executable: str, endpoint: str, env: dict[str, str]) -> None:
        self.executable = executable
        self.endpoint = endpoint
        self.env = dict(env)
        self._created: dict[str, tuple[str, str, list[str]]] = {}

    @classmethod
    async def connect(cls) -> DockerControl:
        executable = shutil.which("docker")
        if executable is None:
            raise DockerFailure("docker_unavailable")
        executable = str(Path(executable).resolve())
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(Path.home()),
            "LANG": "C",
            "LC_ALL": "C",
        }
        raw = await _execute(
            [executable, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            env,
        )
        try:
            endpoint = raw.decode("ascii").strip()
        except UnicodeError:
            raise DockerFailure("docker_endpoint_rejected") from None
        if not re.fullmatch(r"unix:///[A-Za-z0-9_./ -]+", endpoint):
            raise DockerFailure("docker_endpoint_rejected")
        if not Path(endpoint[7:]).is_socket():
            raise DockerFailure("docker_endpoint_rejected")
        return cls(executable, endpoint, env)

    async def command(self, *args: str) -> bytes:
        return await _execute([self.executable, "--host", self.endpoint, *args], self.env)

    def attach_args(self, container_id: str) -> list[str]:
        if not _full_id(container_id):
            raise DockerFailure("invalid_container_id")
        return [
            self.executable,
            "--host",
            self.endpoint,
            "start",
            "--attach",
            "--interactive",
            container_id,
        ]

    async def create(
        self, run_id: str, image_id: str, scenario: str, seed: int, lifetime: int
    ) -> str:
        name = _name(run_id)
        if (
            not _full_id(image_id, image=True)
            or scenario not in SCENARIOS
            or type(seed) is not int
            or not 0 <= seed <= 2**31 - 1
            or type(lifetime) is not int
            or not 5 <= lifetime <= 45
        ):
            raise DockerFailure("invalid_container_configuration")
        argv = ["--scenario", scenario, "--seed", str(seed), "--lifetime", str(lifetime)]
        # Honor cancellation before issuing a create request; shield only the ACK window.
        await anyio.lowlevel.checkpoint()
        try:
            with anyio.CancelScope(shield=True):
                result = await self.command(
                    "create",
                    "--name",
                    name,
                    "--label",
                    f"{PROJECT_LABEL}={PROJECT}",
                    "--label",
                    f"{RUN_LABEL}={run_id}",
                    "--pull",
                    "never",
                    "--interactive",
                    "--network",
                    "none",
                    "--read-only",
                    "--user",
                    "65532:65532",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--cpus",
                    "0.5",
                    "--memory",
                    "128m",
                    "--memory-swap",
                    "128m",
                    "--pids-limit",
                    "32",
                    "--log-driver",
                    "none",
                    "--init",
                    "--restart",
                    "no",
                    "--tmpfs",
                    f"/tmp:{TMPFS}",
                    image_id,
                    *argv,
                )
                container_id = result.decode("ascii").strip()
                if not _full_id(container_id):
                    raise DockerFailure("create_unconfirmed")
                self._created[container_id] = (run_id, image_id, argv)
                return container_id
        except (DockerFailure, UnicodeError):
            raise DockerFailure("create_unconfirmed") from None
        raise DockerFailure("create_unconfirmed")

    async def inspect(self, name: str) -> dict[str, Any] | None:
        is_id = _full_id(name)
        if not is_id and (
            not name.startswith("awb-p003-") or _name(name.removeprefix("awb-p003-")) != name
        ):
            raise DockerFailure("invalid_container_target")
        listing = await self.command(
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--filter",
            f"id={name}" if is_id else f"name=^/{name}$",
            "--format",
            "{{.ID}}",
        )
        if not listing.strip():
            return None
        try:
            container_id = listing.decode("ascii").strip()
            if not _full_id(container_id) or (is_id and container_id != name):
                raise ValueError
            raw = await self.command("container", "inspect", "--format", "{{json .}}", container_id)
            item = json.loads(raw)
            if (
                not isinstance(item, dict)
                or item.get("Id") != container_id
                or (not is_id and item.get("Name") != "/" + name)
            ):
                raise ValueError
            return item
        except (ValueError, UnicodeError, RecursionError):
            raise DockerFailure("docker_inspect_invalid") from None

    @staticmethod
    def _matches(item: dict[str, Any], run_id: str) -> bool:
        config = item.get("Config")
        labels = config.get("Labels") if isinstance(config, dict) else None
        return (
            item.get("Name") == "/" + _name(run_id)
            and isinstance(labels, dict)
            and labels.get(PROJECT_LABEL) == PROJECT
            and labels.get(RUN_LABEL) == run_id
            and isinstance(item.get("Id"), str)
            and _full_id(item["Id"])
        )

    async def verify(self, container_id: str, image_id: str) -> None:
        item = await self.inspect(container_id)
        expected = self._created.get(container_id)
        if item is None or expected is None or expected[1] != image_id:
            raise DockerFailure("container_policy_mismatch")
        run_id, _, argv = expected
        config, host = item.get("Config"), item.get("HostConfig")
        if not isinstance(config, dict) or not isinstance(host, dict):
            raise DockerFailure("container_policy_mismatch")
        required = {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "NanoCpus": 500_000_000,
            "Memory": 134_217_728,
            "MemorySwap": 134_217_728,
            "PidsLimit": 32,
            "Init": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Tmpfs": {"/tmp": TMPFS},
            "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            "LogConfig": {"Type": "none", "Config": {}},
            "PidMode": "",
            "IpcMode": "private",
            "UTSMode": "",
            "UsernsMode": "",
        }
        env = config.get("Env")
        safe_env: dict[str, str] = {}
        if isinstance(env, list):
            for pair in env:
                if not isinstance(pair, str) or "=" not in pair:
                    raise DockerFailure("container_policy_mismatch")
                key, value = pair.split("=", 1)
                if (
                    key in safe_env
                    or key not in ENV_RULES
                    or re.fullmatch(ENV_RULES[key], value) is None
                ):
                    raise DockerFailure("container_policy_mismatch")
                safe_env[key] = value
        valid = (
            self._matches(item, run_id)
            and item.get("Image") == image_id
            and config.get("Image") == image_id
            and config.get("User") == "65532:65532"
            and config.get("Entrypoint") == ENTRYPOINT
            and config.get("Cmd") == argv
            and config.get("OpenStdin") is True
            and config.get("Tty") is False
            and config.get("Volumes") in (None, {})
            and config.get("WorkingDir") == "/tmp"
            and config.get("Healthcheck") in (None, {})
            and set(safe_env) == set(ENV_RULES)
            and all(host.get(key) == value for key, value in required.items())
            and all(
                not host.get(key)
                for key in (
                    "Binds",
                    "Mounts",
                    "VolumesFrom",
                    "CapAdd",
                    "Devices",
                    "DeviceRequests",
                    "PortBindings",
                    "ExtraHosts",
                    "Links",
                    "GroupAdd",
                    "ContainerIDFile",
                    "DeviceCgroupRules",
                    "Sysctls",
                    "CgroupParent",
                )
            )
            and item.get("Mounts") == []
            and isinstance(item.get("State"), dict)
            and item["State"].get("Running") is False
        )
        if not valid:
            raise DockerFailure("container_policy_mismatch")

    async def cleanup(self, run_id: str) -> bool:
        name = _name(run_id)
        try:
            item = await self.inspect(name)
            if item is None:
                return True
            if not self._matches(item, run_id):
                return False
            await self.command("container", "rm", "--force", item["Id"])
            return await self.inspect(name) is None
        except DockerFailure:
            return False

    async def reap(self, run_id: str, apply: bool) -> str:
        name = _name(run_id)
        try:
            item = await self.inspect(name)
            if item is None:
                return "absent"
            if not self._matches(item, run_id) or not isinstance(item.get("State"), dict):
                return "unconfirmed"
            if item["State"].get("Running") is True:
                return "running"
            if item["State"].get("Status") not in ("exited", "dead"):
                return "unconfirmed"
            if not apply:
                return "stopped"
            # No --force: a concurrent start must fail removal rather than kill an active target.
            await self.command("container", "rm", item["Id"])
            return "removed" if await self.inspect(name) is None else "unconfirmed"
        except DockerFailure:
            return "unconfirmed"
