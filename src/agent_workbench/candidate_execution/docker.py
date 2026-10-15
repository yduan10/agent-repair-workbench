"""P0-06's separate single-readonly-mount policy, composed with bounded Docker CLI."""

import re
from pathlib import Path
from typing import Any
from uuid import UUID

import anyio

from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore
from agent_workbench.checker import parse_json_bytes
from agent_workbench.mcp_config import digest
from agent_workbench.runner.docker import (
    ENV_RULES,
    PROJECT_LABEL,
    RUN_LABEL,
    TMPFS,
    DockerControl,
    DockerFailure,
)
from agent_workbench.runner.models import ImageManifest

ENTRYPOINT = ["python", "-I", "-B", "/opt/guardian/supervisor.py"]
PROJECT = "p0-06"
SNAPSHOT_LABEL = "io.agent-workbench.snapshot-sha256"


def verified_image(root: Path) -> ImageManifest:
    """Host-owned prepared artifact only; no download, pull, or build here."""
    path = root / "artifacts/p0-06-image.json"
    if path.is_symlink() or path.stat().st_size > 4096:
        raise ValueError("image_unverified")
    manifest = ImageManifest.model_validate(parse_json_bytes(path.read_bytes()))
    parts = []
    for name in ("Dockerfile", "supervisor.py", "prepare.py"):
        source = root / "containers/p0_06" / name
        if source.is_symlink() or source.stat().st_size > 65_536:
            raise ValueError("image_unverified")
        parts.append(name.encode() + b"\0" + source.read_bytes())
    if digest(b"\0".join(parts)) != manifest.source_sha256:
        raise ValueError("image_unverified")
    return manifest


class CandidateDockerControl:
    """One invocation owns one already-registered attempt UUID, never a user command."""

    def __init__(
        self,
        control: DockerControl,
        snapshot: SnapshotHandle,
        image: ImageManifest,
        scenario: str,
        attempt_id: str,
    ) -> None:
        if str(UUID(attempt_id)) != attempt_id or scenario not in ("pass", "wrong_type"):
            raise ValueError("invalid_attempt")
        self.control, self.snapshot, self.image = control, snapshot, image
        self.attempt_id = attempt_id
        self.name = "awb-p006-" + attempt_id
        self.argv = ["--scenario", scenario]
        self.root = str(snapshot.root.absolute())
        # Docker mount syntax has separators, although no shell is involved.
        if any(c in self.root for c in (",", "\n", "\r")):
            raise ValueError("invalid_snapshot_root")
        self.started = False
        self.ambiguous = False
        self.container_id: str | None = None

    async def inspect(self) -> dict[str, Any] | None:
        raw = await self.control.command(
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--filter",
            f"name=^/{self.name}$",
            "--format",
            "{{.ID}}",
        )
        if not raw.strip():
            return None
        try:
            cid = raw.decode("ascii").strip()
            if re.fullmatch(r"[a-f0-9]{64}", cid) is None:
                raise ValueError
            item = await self.control.inspect(cid)
            if item is None or not self.matches(item):
                raise ValueError
            if self.container_id is not None and cid != self.container_id:
                raise ValueError
            return item
        except (ValueError, UnicodeError):
            raise DockerFailure("container_identity_mismatch") from None

    def matches(self, item: dict[str, Any]) -> bool:
        config = item.get("Config", {})
        labels = config.get("Labels", {}) if isinstance(config, dict) else {}
        return (
            isinstance(labels, dict)
            and labels.get(PROJECT_LABEL) == PROJECT
            and labels.get(RUN_LABEL) == self.attempt_id
            and labels.get(SNAPSHOT_LABEL) == self.snapshot.ref.tree_sha256
            and item.get("Name") == "/" + self.name
            and item.get("Image") == self.image.image_id
        )

    async def create(self) -> str:
        SnapshotStore(self.snapshot.root.parent).verify(self.snapshot)
        # Never claim an old attempt, including one left by a killed owner.
        if await self.inspect() is not None:
            raise DockerFailure("attempt_already_exists")
        await anyio.lowlevel.checkpoint()
        self.started = True
        try:
            with anyio.CancelScope(shield=True):
                raw = await self.control.command(
                    "create",
                    "--name",
                    self.name,
                    "--label",
                    f"{PROJECT_LABEL}={PROJECT}",
                    "--label",
                    f"{RUN_LABEL}={self.attempt_id}",
                    "--label",
                    f"{SNAPSHOT_LABEL}={self.snapshot.ref.tree_sha256}",
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
                    "--mount",
                    f"type=bind,source={self.root},target=/opt/subject,readonly",
                    self.image.image_id,
                    *self.argv,
                )
                cid = raw.decode("ascii").strip()
                if re.fullmatch(r"[a-f0-9]{64}", cid) is None:
                    raise ValueError
                self.container_id = cid
                return cid
        except (DockerFailure, UnicodeError, ValueError):
            self.ambiguous = True
            raise DockerFailure("create_unconfirmed") from None
        self.ambiguous = True
        raise DockerFailure("create_unconfirmed")

    async def verify(self) -> None:
        item = await self.inspect()
        if item is None or self.container_id is None:
            raise DockerFailure("container_policy_mismatch")
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
            "Mounts": [
                {"Type": "bind", "Source": self.root, "Target": "/opt/subject", "ReadOnly": True}
            ],
        }
        environment = config.get("Env")
        safe_env: dict[str, str] = {}
        if isinstance(environment, list):
            for pair in environment:
                if not isinstance(pair, str) or "=" not in pair:
                    raise DockerFailure("container_policy_mismatch")
                key, value = pair.split("=", 1)
                if (
                    key in safe_env
                    or key not in ENV_RULES
                    or not re.fullmatch(ENV_RULES[key], value)
                ):
                    raise DockerFailure("container_policy_mismatch")
                safe_env[key] = value
        mounts = item.get("Mounts")
        valid_mount = (
            isinstance(mounts, list)
            and len(mounts) == 1
            and isinstance(mounts[0], dict)
            and mounts[0].get("Type") == "bind"
            and mounts[0].get("Source") == self.root
            and mounts[0].get("Destination") == "/opt/subject"
            and mounts[0].get("RW") is False
            and mounts[0].get("Propagation") == "rprivate"
        )
        valid = (
            self.matches(item)
            and config.get("Image") == self.image.image_id
            and config.get("User") == "65532:65532"
            and config.get("Entrypoint") == ENTRYPOINT
            and config.get("Cmd") == self.argv
            and config.get("OpenStdin") is True
            and config.get("Tty") is False
            and config.get("Volumes") in (None, {})
            and config.get("WorkingDir") == "/tmp"
            and config.get("Healthcheck") in (None, {})
            and set(safe_env) == set(ENV_RULES)
            and valid_mount
            and all(host.get(k) == v for k, v in required.items())
            and all(
                not host.get(k)
                for k in (
                    "Binds",
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
            and isinstance(item.get("State"), dict)
            and item["State"].get("Running") is False
        )
        if not valid:
            raise DockerFailure("container_policy_mismatch")

    async def cleanup(self) -> bool:
        if not self.started:
            return True
        item = await self.inspect()
        if item is not None:
            await self.control.command("container", "rm", "--force", item["Id"])
        return await self.inspect() is None and not self.ambiguous
