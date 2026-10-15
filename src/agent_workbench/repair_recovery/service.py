"""Read-only by default; explicit apply removes only positively identified containers.

A task fence covers the complete inspect/reap interval. Ledger reconciliation uses
the same task fence and original CAS through the complete operation.
No execution or budget reservation is replayed.
"""

import asyncio
import re
from pathlib import Path
from typing import Final, Literal

from pydantic import ConfigDict, Field

from agent_workbench.candidate_execution.docker import (
    ENTRYPOINT,
    CandidateDockerControl,
    verified_image,
)
from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore
from agent_workbench.orchestration.contracts import Contract, Identifier
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.runner.docker import DockerControl, DockerFailure
from agent_workbench.runner.models import ImageManifest

from .inventory import Inventory, RecoveryInventory, Target

BASE: Final = "python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"


class Resource(Contract):
    model_config = ConfigDict(frozen=False, validate_assignment=True)
    attempt_id: Identifier
    tool: Literal["T05", "T07"]
    slot: str
    state: Literal["absent", "present", "removed", "unknown"] = "unknown"
    running: bool | None = None
    error: Literal["IDENTITY_UNVERIFIED", "CLEANUP_UNCONFIRMED"] | None = None


class RecoveryReport(Contract):
    model_config = ConfigDict(frozen=False, validate_assignment=True)
    schema_version: Literal[1] = 1
    task_id: Identifier
    mode: Literal["inspect", "apply"]
    outcome: str | None = None
    resources: list[Resource] = Field(default_factory=list)
    requires_reconcile: bool = False
    ledger_reconciled: bool = False
    error: str | None = None

    def exit_code(self) -> int:
        return (
            2
            if (
                self.error
                or self.requires_reconcile
                or any(r.state not in ("absent", "removed") for r in self.resources)
            )
            else 0
        )


class RecoveryService:
    def __init__(
        self, store: RecoveryInventory, image_root: Path, control: DockerControl | None = None
    ) -> None:
        self.store, self.image_root, self.control = store, image_root, control

    async def controller(self, target: Target) -> CandidateDockerControl:
        if self.control is None:
            self.control = await DockerControl.connect()
        handle = SnapshotHandle(
            target.snapshot, self.store.directory / "repair-snapshots" / target.snapshot.snapshot_id
        )
        return CandidateDockerControl(
            self.control,
            handle,
            ImageManifest(
                image_id=target.image_id, source_sha256=target.image_source_sha256, base_digest=BASE
            ),
            target.scenario,
            target.attempt_id,
        )

    async def inspect(self, controller: CandidateDockerControl) -> tuple[str, bool] | None:
        raw = await controller.control.command(
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--filter",
            f"name=^/{controller.name}$",
            "--format",
            "{{.ID}}",
        )
        if not raw.strip():
            return None
        selected = raw.decode("ascii").strip()
        if re.fullmatch(r"[a-f0-9]{64}", selected) is None:
            raise DockerFailure("container_identity_mismatch")
        item = await controller.control.inspect(selected)
        if item is None or item.get("Id") != selected or not controller.matches(item):
            raise DockerFailure("container_identity_mismatch")
        # An absent identity needs no surviving image/snapshot. A present resource
        # requires both independently verified host evidence and exact Docker binding.
        image = verified_image(self.image_root)
        if image != controller.image:
            raise DockerFailure("container_identity_mismatch")
        SnapshotStore(controller.snapshot.root.parent).verify(controller.snapshot)
        cid, config, mounts, state = (
            item.get("Id"),
            item.get("Config"),
            item.get("Mounts"),
            item.get("State"),
        )
        if not (
            isinstance(cid, str)
            and re.fullmatch(r"[a-f0-9]{64}", cid)
            and isinstance(config, dict)
            and config.get("Image") == image.image_id
            and config.get("Cmd") == controller.argv
            and config.get("Entrypoint") == ENTRYPOINT
            and isinstance(state, dict)
            and isinstance(state.get("Running"), bool)
            and isinstance(mounts, list)
            and len(mounts) == 1
            and isinstance(mounts[0], dict)
            and mounts[0].get("Type") == "bind"
            and mounts[0].get("Source") == controller.root
            and mounts[0].get("Destination") == "/opt/subject"
            and mounts[0].get("RW") is False
            and mounts[0].get("Propagation") == "rprivate"
        ):
            raise DockerFailure("container_identity_mismatch")
        if controller.container_id is not None and controller.container_id != cid:
            raise DockerFailure("container_identity_mismatch")
        controller.container_id = cid
        return cid, state["Running"]

    async def recover(self, task_id: str, *, apply: bool = False) -> RecoveryReport:
        try:
            with RepairFence(self.store.directory, task_id) as fence:
                return await self.recover_held(task_id, fence=fence, apply=apply)
        except Exception as error:
            return RecoveryReport(
                task_id=task_id,
                mode="apply" if apply else "inspect",
                error="OWNER_ACTIVE"
                if getattr(error, "code", None) == "repair_busy"
                else "RECOVERY_UNCONFIRMED",
            )

    async def recover_held(
        self,
        task_id: str,
        *,
        fence: RepairFence,
        apply: bool = False,
    ) -> RecoveryReport:
        """Internal entry: caller keeps the same task fence through reconciliation."""
        with fence.guard(self.store.directory, task_id):
            return await self._recover(task_id, fence=fence, apply=apply)

    async def _recover(
        self,
        task_id: str,
        *,
        fence: RepairFence,
        apply: bool,
    ) -> RecoveryReport:
        report = RecoveryReport(task_id=task_id, mode="apply" if apply else "inspect")
        inventory: Inventory | None = None
        try:
            # Busy/SIGSTOP owners are rejected before even inspecting Docker.
            with fence.guard(self.store.directory, task_id):
                inventory = self.store.inventory(task_id)
                report.outcome = inventory.saved.task.outcome
                report.requires_reconcile = inventory.saved.task.phase != "finished"
                async with asyncio.timeout(120):
                    controllers = []
                    for target in inventory.targets:
                        row = Resource(
                            attempt_id=target.attempt_id, tool=target.tool, slot=target.slot
                        )
                        report.resources.append(row)
                        try:
                            controller = await self.controller(target)
                            found = await self.inspect(controller)
                            row.state = "present" if found else "absent"
                            row.running = found[1] if found else None
                            controllers.append(controller)
                        except Exception:
                            row.error = "IDENTITY_UNVERIFIED"
                    # No removal until every persisted identity has passed preflight.
                    if any(row.state == "unknown" for row in report.resources):
                        report.error = "RESOURCE_UNVERIFIED"
                        return report
                    if not apply:
                        return report
                    for row, controller in zip(report.resources, controllers, strict=True):
                        try:
                            found = await self.inspect(controller)
                            if found:
                                await controller.control.command(
                                    "container", "rm", "--force", found[0]
                                )
                                if await self.inspect(controller) is not None:
                                    raise DockerFailure("cleanup_unconfirmed")
                                row.state = "removed"
                            else:
                                row.state = "absent"
                        except Exception:
                            row.state, row.error = "unknown", "CLEANUP_UNCONFIRMED"
                            report.error = "RESOURCE_UNVERIFIED"
                            return report
            if report.requires_reconcile:
                # Held-fence store recovery preserves pending request semantics.
                # Never reconcile a terminal task: keep verified/cancelled history intact.
                method = {
                    "comparison": self.store.reconcile_comparison_held,
                    "reproduction": self.store.reconcile_reproduction_held,
                }.get(inventory.pending_operation or "", self.store.reconcile_held)
                updated = method(
                    task_id,
                    expected_revision=inventory.saved.task.revision,
                    expected_sha256=inventory.saved.task_sha256,
                    fence=fence,
                )
                report.outcome = updated.task.outcome
                report.requires_reconcile = False
                report.ledger_reconciled = True
            return report
        except Exception as error:
            # Never disclose raw Docker, snapshot paths or ledger exception text.
            report.error = (
                "OWNER_ACTIVE"
                if getattr(error, "code", None) == "repair_busy"
                else "RECOVERY_UNCONFIRMED"
            )
            return report
