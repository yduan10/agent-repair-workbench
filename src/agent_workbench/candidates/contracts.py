"""Public snapshot metadata excludes host paths and executable verdicts."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agent_workbench.orchestration.contracts import Contract, Digest, Identifier, Version


class CandidateError(Exception):
    """Only fixed codes may cross the public boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CandidatePatch(Contract):
    schema_version: Version = 1
    path: Literal["source/server.py"] = "source/server.py"
    expected_baseline_hash: Digest
    expected_file_hash: Digest
    replacement: Annotated[str, Field(min_length=1, max_length=8192)]

    @model_validator(mode="after")
    def utf8_limit(self) -> Self:
        try:
            raw = self.replacement.encode("utf-8")
        except UnicodeError:
            raise ValueError("invalid_utf8") from None
        if len(raw) > 8192 or b"\x00" in raw:
            raise ValueError("replacement_limit")
        return self


class SnapshotRef(Contract):
    schema_version: Version = 1
    snapshot_id: Identifier
    kind: Literal["baseline", "candidate"]
    file: Literal["server.py"] = "server.py"
    manifest_sha256: Digest
    file_sha256: Digest
    tree_sha256: Digest
    baseline_id: Identifier | None = None
    baseline_tree_sha256: Digest | None = None
    patch_sha256: Digest | None = None

    @model_validator(mode="after")
    def provenance(self) -> Self:
        fields = (self.baseline_id, self.baseline_tree_sha256, self.patch_sha256)
        if self.kind == "baseline" and any(value is not None for value in fields):
            raise ValueError("baseline_provenance_invalid")
        if self.kind == "candidate" and (
            any(value is None for value in fields) or self.baseline_id == self.snapshot_id
        ):
            raise ValueError("candidate_provenance_invalid")
        return self


class SafeDiff(Contract):
    schema_version: Version = 1
    baseline: SnapshotRef
    candidate: SnapshotRef
    path: Literal["source/server.py"] = "source/server.py"
    unified_diff: Annotated[str, Field(max_length=65536)]
