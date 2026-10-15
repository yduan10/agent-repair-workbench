"""P0-06 repair requests are limited structurally to this role's permissions."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from agent_workbench.orchestration.contracts import Contract, Version
from agent_workbench.repair_contracts.common import RoleConclusion
from agent_workbench.repair_contracts.tools import (
    ApplyCandidate,
    ReadContract,
    ReadEvidence,
    ReadSource,
)

type RepairRequest = Annotated[
    ReadEvidence | ReadContract | ReadSource | ApplyCandidate,
    Field(discriminator="tool"),
]


class RepairToolDecision(Contract):
    schema_version: Version = 1
    action: Literal["request_tool"]
    request: RepairRequest


type RepairOutput = Annotated[RepairToolDecision | RoleConclusion, Field(discriminator="action")]
ADAPTER = TypeAdapter[RepairOutput](RepairOutput)
