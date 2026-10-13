"""Diagnosis outputs are hypotheses, never self-certified root causes."""

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


class DiagnosisConclusion(Contract):
    schema_version: Version = 1
    action: Literal["conclude"]
    assessment: Literal["hypothesis", "inconclusive"]
    reason_code: Reason
    evidence_refs: References

    @model_validator(mode="after")
    def supporting_evidence(self) -> Self:
        unique_evidence(self.evidence_refs)
        if self.assessment == "hypothesis" and not self.evidence_refs:
            raise ValueError("hypothesis_requires_evidence")
        return self


type DiagnosisOutput = Annotated[ToolDecision | DiagnosisConclusion, Field(discriminator="action")]
