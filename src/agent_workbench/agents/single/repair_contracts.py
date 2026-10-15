"""P0-06 single requests are limited structurally to this role's permissions."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from agent_workbench.orchestration.contracts import Contract, Version
from agent_workbench.repair_contracts.common import RoleConclusion
from agent_workbench.repair_contracts.tools import (
    ApplyCandidate,
    CheckContract,
    CompareCandidate,
    ReadContract,
    ReadEvidence,
    ReadSource,
    Reproduce,
)

type SingleRequest = Annotated[
    ReadEvidence
    | ReadContract
    | ReadSource
    | CheckContract
    | Reproduce
    | ApplyCandidate
    | CompareCandidate,
    Field(discriminator="tool"),
]


class SingleToolDecision(Contract):
    schema_version: Version = 1
    action: Literal["request_tool"]
    request: SingleRequest


type SingleOutput = Annotated[SingleToolDecision | RoleConclusion, Field(discriminator="action")]
ADAPTER = TypeAdapter[SingleOutput](SingleOutput)
