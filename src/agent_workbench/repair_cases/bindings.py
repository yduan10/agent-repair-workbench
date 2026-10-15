"""Resolve evaluator policy only from a fully bound durable baseline reference."""

from agent_workbench.candidates.contracts import CandidateError, SnapshotRef
from agent_workbench.mcp_config import canonical, digest

from .profiles import CaseProfile, profile_for_manifest


def validate_baseline_binding(ref: SnapshotRef) -> CaseProfile:
    try:
        ref = SnapshotRef.model_validate_json(ref.model_dump_json())
        profile = profile_for_manifest(ref.manifest_sha256)
        expected_tree = digest(canonical({"server.py": profile.source_sha256}))
        if (
            ref.kind != "baseline"
            or ref.file_sha256 != profile.source_sha256
            or ref.tree_sha256 != expected_tree
        ):
            raise ValueError
        return profile
    except ValueError:
        raise CandidateError("SOURCE_MANIFEST_MISMATCH") from None
