"""P0-06 verification requests are limited structurally to this role's permissions."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from agent_workbench.orchestration.contracts import Contract, Version
from agent_workbench.repair_contracts.common import RoleConclusion
from agent_workbench.repair_contracts.tools import (
    CheckContract,
    CompareCandidate,
    ReadContract,
    ReadEvidence,
    ReadSource,
    Reproduce,
)

type VerificationRequest = Annotated[
    ReadEvidence | ReadContract | ReadSource | CheckContract | Reproduce | CompareCandidate,
    Field(discriminator="tool"),
]


class VerificationToolDecision(Contract):
    schema_version: Version = 1
    action: Literal["request_tool"]
    request: VerificationRequest


type VerificationOutput = Annotated[
    VerificationToolDecision | RoleConclusion, Field(discriminator="action")
]
ADAPTER = TypeAdapter[VerificationOutput](VerificationOutput)
