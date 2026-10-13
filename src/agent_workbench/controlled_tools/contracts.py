"""P0-05a request schemas only; no executable tools or arbitrary shell arguments."""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from agent_workbench.orchestration.contracts import (
    Contract,
    Digest,
    EvidenceRef,
    Identifier,
    Name,
    Version,
)


def relative_path(value: str) -> str:
    if (
        value.startswith("/")
        or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
        or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)
    ):
        raise ValueError("invalid_relative_path")
    return value


RelativePath = Annotated[str, Field(min_length=1, max_length=512), AfterValidator(relative_path)]


class Request(Contract):
    schema_version: Version = 1
    request_id: Identifier


class ReadEvidence(Request):
    tool: Literal["read_evidence"]
    evidence_ref: EvidenceRef
    section: Literal["summary", "findings", "events"]


class ReadContract(Request):
    tool: Literal["read_contract"]
    profile_id: Name
    tool_name: Name
    revision: Digest


class ReadSource(Request):
    tool: Literal["read_source"]
    snapshot_id: Digest
    relative_path: RelativePath
    start_line: Annotated[int, Field(ge=1, le=1_000_000)]
    end_line: Annotated[int, Field(ge=1, le=1_000_000)]

    @model_validator(mode="after")
    def line_range(self) -> Self:
        if not 0 <= self.end_line - self.start_line < 200:
            raise ValueError("line_range_exceeded")
        return self


class CheckContract(Request):
    tool: Literal["check_contract"]
    case_id: Identifier
    contract_revision: Digest


class Reproduce(Request):
    tool: Literal["request_reproduction"]
    approved_case_id: Identifier
    profile_revision: Digest


type ToolRequest = Annotated[
    ReadEvidence | ReadContract | ReadSource | CheckContract | Reproduce,
    Field(discriminator="tool"),
]
TOOL_MODELS = (ReadEvidence, ReadContract, ReadSource, CheckContract, Reproduce)


def target_key(request: ToolRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"schema_version", "request_id"})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


class ToolDecision(Contract):
    schema_version: Version = 1
    action: Literal["request_tool"]
    request: ToolRequest
