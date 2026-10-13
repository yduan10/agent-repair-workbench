"""Untrusted ephemeral proposals, never applied or persisted by P0-05a."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agent_workbench.controlled_tools.contracts import RelativePath, ToolDecision
from agent_workbench.orchestration.contracts import (
    Contract,
    Digest,
    References,
    Version,
    unique_evidence,
)


class Edit(Contract):
    path: RelativePath
    base_sha256: Digest
    replacement: Annotated[str, Field(max_length=8192)]


class RepairConclusion(Contract):
    schema_version: Version = 1
    action: Literal["conclude"]
    disposition: Literal["proposal_only", "cannot_propose"]
    evidence_refs: References
    edits: Annotated[tuple[Edit, ...], Field(max_length=5)]

    @model_validator(mode="after")
    def bounded_proposal(self) -> Self:
        unique_evidence(self.evidence_refs)
        if self.disposition == "proposal_only" and (not self.edits or not self.evidence_refs):
            raise ValueError("proposal_requires_edit_and_evidence")
        if self.disposition == "cannot_propose" and self.edits:
            raise ValueError("unexpected_edits")
        if len({edit.path for edit in self.edits}) != len(self.edits):
            raise ValueError("duplicate_edit_path")
        if sum(len(edit.replacement.encode("utf-8")) for edit in self.edits) > 32768:
            raise ValueError("proposal_size_exceeded")
        return self


type RepairOutput = Annotated[ToolDecision | RepairConclusion, Field(discriminator="action")]
