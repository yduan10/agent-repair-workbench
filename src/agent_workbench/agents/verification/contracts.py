"""Read-only explanation contract. The model cannot certify a candidate."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agent_workbench.controlled_tools.contracts import ToolDecision
from agent_workbench.orchestration.contracts import (
    Contract,
    Reason,
    References,
    Version,
    unique_evidence,
)


class VerificationConclusion(Contract):
    schema_version: Version = 1
    action: Literal["conclude"]
    assessment: Literal["needs_evidence", "proposal_reviewed"]
    reason_code: Reason
    evidence_refs: References

    @model_validator(mode="after")
    def evidence_required(self) -> Self:
        unique_evidence(self.evidence_refs)
        if self.assessment == "proposal_reviewed" and not self.evidence_refs:
            raise ValueError("review_requires_evidence")
        return self


type VerificationOutput = Annotated[
    ToolDecision | VerificationConclusion, Field(discriminator="action")
]
