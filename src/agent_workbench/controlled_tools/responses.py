"""P0-05b: bounded, metadata-only controlled tool envelopes (source is transient)."""

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from agent_workbench.mcp_config import canonical
from agent_workbench.orchestration.contracts import (
    Contract,
    Digest,
    Identifier,
    References,
    Version,
    unique_evidence,
)

ToolName = Literal[
    "read_evidence", "read_contract", "read_source", "check_contract", "request_reproduction"
]
ErrorCode = Literal[
    "INVALID_INPUT",
    "PERMISSION_DENIED",
    "STALE_VERSION",
    "BUDGET_EXCEEDED",
    "RESOURCE_LIMIT",
    "TOOL_FAILURE",
    "RESULT_UNKNOWN",
    "ARTIFACT_MISMATCH",
    "REQUEST_CONFLICT",
]


class ToolResponse(Contract):
    schema_version: Version = 1
    request_id: Identifier
    tool: ToolName
    status: Literal["ok", "rejected", "failed", "outcome_unknown"]
    error_code: ErrorCode | None = None
    evidence_refs: References = ()
    observed_versions: Annotated[tuple[Digest, ...], Field(max_length=8)] = ()
    truncated: Literal[False] = False
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        unique_evidence(self.evidence_refs)
        if (self.status == "ok") != (self.error_code is None):
            raise ValueError("invalid_tool_status")
        if len(canonical(self.model_dump(mode="json"))) > 65_536:
            raise ValueError("tool_response_limit")
        return self


class ResourceError(Exception):
    """Only fixed codes cross the tool boundary."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code)
        self.code = code
