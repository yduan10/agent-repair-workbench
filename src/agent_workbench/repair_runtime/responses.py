"""Bounded model-facing feedback; full oracle evidence stays in the host ledger."""

from dataclasses import dataclass, field
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from agent_workbench.controlled_tools.responses import ErrorCode
from agent_workbench.mcp_config import canonical
from agent_workbench.orchestration.contracts import (
    Contract,
    Digest,
    Identifier,
    References,
    Version,
    unique_evidence,
)
from agent_workbench.repair_store.models import Mutation


class RepairToolResponse(Contract):
    schema_version: Version = 1
    request_id: Identifier
    tool: Literal[
        "read_evidence",
        "read_contract",
        "read_source",
        "check_contract",
        "request_reproduction",
        "apply_candidate",
        "compare_candidate",
    ]

    status: Literal["ok", "rejected", "failed", "outcome_unknown"]
    error_code: ErrorCode | None = None
    evidence_refs: References = ()
    observed_versions: Annotated[tuple[Digest, ...], Field(max_length=8)] = ()
    truncated: Literal[False] = False
    payload: dict[str, JsonValue] = Field(default_factory=dict, repr=False)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        unique_evidence(self.evidence_refs)
        if (self.status == "ok") != (self.error_code is None):
            raise ValueError("invalid_tool_status")
        if len(canonical(self.model_dump(mode="json"))) > 65536:
            raise ValueError("tool_response_limit")
        return self


@dataclass(frozen=True)
class RepairToolResult:
    response: RepairToolResponse = field(repr=False)
    cursor: Mutation
    cancelled: bool = False
    replayed: bool = False
    requires_reconcile: bool = False
