"""P0-06 tool requests. The host supplies paths, attempts, versions and permissions."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agent_workbench.candidates.contracts import CandidatePatch
from agent_workbench.controlled_tools.contracts import (
    TOOL_MODELS as READ_TOOL_MODELS,
)
from agent_workbench.controlled_tools.contracts import (
    CheckContract,
    ReadContract,
    ReadEvidence,
    ReadSource,
    Reproduce,
    Request,
)
from agent_workbench.orchestration.contracts import (
    Digest,
    EvidenceRef,
    Identifier,
    unique_evidence,
)

__all__ = [
    "ApplyCandidate",
    "CheckContract",
    "CompareCandidate",
    "ReadContract",
    "ReadEvidence",
    "ReadSource",
    "RepairToolRequest",
    "Reproduce",
    "TOOL_MODELS",
]

SupportingEvidence = Annotated[tuple[EvidenceRef, ...], Field(min_length=1, max_length=32)]


class ApplyCandidate(Request):
    tool: Literal["apply_candidate"]
    candidate_id: Identifier
    expected_baseline_hash: Digest
    expected_file_hash: Digest
    replacement: Annotated[str, Field(min_length=1, max_length=8192, repr=False)]
    evidence_refs: SupportingEvidence

    @model_validator(mode="after")
    def bounded_patch(self) -> Self:
        unique_evidence(self.evidence_refs)
        # Reuse the authoritative patch's byte and encoding checks without exposing its path.
        CandidatePatch(
            expected_baseline_hash=self.expected_baseline_hash,
            expected_file_hash=self.expected_file_hash,
            replacement=self.replacement,
        )
        return self


class CompareCandidate(Request):
    tool: Literal["compare_candidate"]
    candidate_id: Identifier
    expected_candidate_tree_hash: Digest
    evidence_refs: SupportingEvidence

    @model_validator(mode="after")
    def unique_refs(self) -> Self:
        unique_evidence(self.evidence_refs)
        return self


type RepairToolRequest = Annotated[
    ReadEvidence
    | ReadContract
    | ReadSource
    | CheckContract
    | Reproduce
    | ApplyCandidate
    | CompareCandidate,
    Field(discriminator="tool"),
]
TOOL_MODELS = (*READ_TOOL_MODELS, ApplyCandidate, CompareCandidate)
