"""P0-06 diagnosis requests are limited structurally to this role's permissions."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from agent_workbench.orchestration.contracts import Contract, Version
from agent_workbench.repair_contracts.common import RoleConclusion
from agent_workbench.repair_contracts.tools import (
    CheckContract,
    ReadContract,
    ReadEvidence,
    ReadSource,
    Reproduce,
)

type DiagnosisRequest = Annotated[
    ReadEvidence | ReadContract | ReadSource | CheckContract | Reproduce,
    Field(discriminator="tool"),
]


class DiagnosisToolDecision(Contract):
    schema_version: Version = 1
    action: Literal["request_tool"]
    request: DiagnosisRequest


type DiagnosisOutput = Annotated[
    DiagnosisToolDecision | RoleConclusion, Field(discriminator="action")
]
ADAPTER = TypeAdapter[DiagnosisOutput](DiagnosisOutput)
