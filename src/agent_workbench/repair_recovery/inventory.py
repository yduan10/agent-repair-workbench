"""Validated, bounded inventory. Private ledger reads stay inside the store boundary."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from agent_workbench.candidate_execution.compare import SLOTS
from agent_workbench.candidates.contracts import SnapshotRef
from agent_workbench.repair_store.models import Mutation
from agent_workbench.repair_store.reproductions import ReproductionStore
from agent_workbench.run_store.models import StoreError


@dataclass(frozen=True)
class Target:
    attempt_id: str
    tool: Literal["T05", "T07"]
    slot: str
    snapshot: SnapshotRef
    scenario: str
    image_id: str
    image_source_sha256: str


@dataclass(frozen=True)
class Inventory:
    saved: Mutation
    pending_operation: str | None
    targets: tuple[Target, ...]


class RecoveryInventory(ReproductionStore):
    def inventory(self, task_id: str) -> Inventory:
        if str(UUID(task_id)) != task_id:
            raise ValueError("invalid_task")
        saved = self.get(task_id)
        # _read verifies hashes, request ownership, identities and event coherence.
        with self._base._transaction() as connection:
            _, requests, _ = self._read(connection, task_id)
        targets = []
        pending = None
        for request in requests.values():
            if request.status == "pending":
                pending = request.operation
            if request.operation == "reproduction":
                record = self.get_reproduction(task_id, request.request_id)
                if record is None:
                    raise StoreError("store_corrupt")
                p = record.plan
                targets.append(
                    Target(
                        p.attempt_id,
                        "T05",
                        "baseline_wrong_type",
                        p.baseline,
                        p.scenario,
                        p.image_id,
                        p.image_source_sha256,
                    )
                )
        for comparison in self.comparisons(task_id):
            plan = comparison.plan
            for i, attempt in enumerate(plan.attempts):
                targets.append(
                    Target(
                        attempt,
                        "T07",
                        SLOTS[i],
                        plan.baseline if i < 2 else plan.candidate,
                        "wrong_type" if i % 2 == 0 else "pass",
                        plan.image_id,
                        plan.image_source_sha256,
                    )
                )
        if len(targets) > 80 or len({t.attempt_id for t in targets}) != len(targets):
            raise StoreError("store_corrupt")
        return Inventory(saved, pending, tuple(targets))
