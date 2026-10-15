"""Explicit recovery with positive create termination evidence and final ledger CAS.

An absent container is never, by itself, proof that a delayed create cannot arrive.
No user-supplied proof, forced unlock, background retry or report fabrication exists.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from agent_workbench.candidate_execution.models import OracleReport
from agent_workbench.repair_recovery.service import RecoveryReport, RecoveryService, Resource
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.run_store.models import StoreError
from agent_workbench.runner.docker import DockerControl, DockerFailure

from .fencing import RepairWebFence
from .store import WebRepairStore


def terminated(report: OracleReport | None) -> bool:
    if report is None or report.error == "attach_cleanup_unconfirmed":
        return False
    if report.cleanup == "removed":
        return True
    # These host branches return before any Docker create is sent. Other errors
    # (notably docker_failure) could mean an existing identity, so stay closed.
    return report.cleanup == "not_created" and report.error in {
        "invalid_budget",
        "oracle_unverified",
        "unsupported_sdk",
        "image_unverified",
    }


@dataclass(frozen=True)
class ReleaseResult:
    recovery: RecoveryReport
    released: bool = False


class WebRepairRecovery(RecoveryService):
    store: WebRepairStore

    def __init__(
        self,
        store: WebRepairStore,
        image_root: Path,
        control: DockerControl | None = None,
    ) -> None:
        super().__init__(store, image_root, control)

    async def release_checked(
        self,
        task_id: str,
        *,
        owner: RepairWebFence,
        fence: RepairFence,
        apply: bool = False,
    ) -> ReleaseResult:
        report = RecoveryReport(task_id=task_id, mode="apply" if apply else "inspect")
        try:
            with owner.guard(self.store.directory), fence.guard(self.store.directory, task_id):
                if apply:
                    self.store.retire_unstarted(task_id, owner=owner, fence=fence)
                before, _, _ = self.store.release_state(task_id)
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
                        controller = await self.controller(target)
                        found = await self.inspect(controller)
                        row.state, row.running = (
                            ("present", found[1]) if found else ("absent", None)
                        )
                        controllers.append(controller)
                    # Preflight every identity before deleting even one container.
                    if not apply:
                        return ReleaseResult(report)
                    for row, controller in zip(report.resources, controllers, strict=True):
                        found = await self.inspect(controller)
                        if found:
                            await controller.control.command("container", "rm", "--force", found[0])
                            if await self.inspect(controller) is not None:
                                raise DockerFailure("cleanup_unconfirmed")
                            row.state = "removed"
                    if self.store.release_state(task_id)[0] != before:
                        raise StoreError("recovery_required")
                    if report.requires_reconcile:
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
                    stamp, settled, evidence = self.store.release_state(task_id)
                    if not settled or set(evidence) != {t.attempt_id for t in inventory.targets}:
                        raise StoreError("recovery_required")
                    for row, controller in zip(report.resources, controllers, strict=True):
                        proof = evidence[row.attempt_id]
                        if (
                            (not terminated(proof) and row.state != "removed")
                            or (proof is not None and proof.error == "attach_cleanup_unconfirmed")
                            or await self.inspect(controller) is not None
                        ):
                            raise StoreError("recovery_required")
                    self.store._release_cas(task_id, stamp, owner=owner, fence=fence)
                    return ReleaseResult(report, released=True)
        except (Exception, asyncio.CancelledError):
            # Unknown outcomes retain active. Never disclose raw paths or Docker errors.
            report.error = "RECOVERY_UNCONFIRMED"
            return ReleaseResult(report)
