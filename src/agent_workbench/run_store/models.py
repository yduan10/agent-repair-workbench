"""P0-04 public views. Lease credentials are absent from every read DTO."""

from typing import Literal

from agent_workbench.models import StrictModel

RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "outcome_unknown"]
ExecutorState = Literal["absent", "running", "stopped", "unavailable", "mismatch"]
EventKind = Literal["created", "claimed", "finished", "reconciled"]


class RunView(StrictModel):
    run_id: str
    attempt_id: str | None
    status: RunStatus
    version: int
    created_at: float
    updated_at: float
    lease_until: float | None
    profile: str
    scenario: str
    config_sha256: str
    case_sha256: str
    report_sha256: str | None
    executor_state: ExecutorState | None


class EventView(StrictModel):
    event_id: str
    version: int
    kind: EventKind
    created_at: float


class RunDetail(StrictModel):
    run: RunView
    events: list[EventView]


class Claim(StrictModel):
    run: RunView
    token: str


class StoreError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
