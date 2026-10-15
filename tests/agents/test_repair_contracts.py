"""P0-06 B3a: R03/R07/R09/A04/A05 contract boundaries, not host execution tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_workbench.controlled_tools.contracts import TOOL_MODELS as LEGACY_TOOLS
from agent_workbench.orchestration.codec import decode_role as decode_legacy
from agent_workbench.orchestration.policy import PolicyError
from agent_workbench.repair_contracts.codec import decode_role
from agent_workbench.repair_contracts.common import RoleConclusion
from agent_workbench.repair_contracts.tools import TOOL_MODELS, ApplyCandidate

ID = "00000000-0000-0000-0000-000000000001"
CANDIDATE = "00000000-0000-0000-0000-000000000002"
REF = {"evidence_id": ID, "sha256": "a" * 64}
REQUESTS = [
    {"tool": "read_evidence", "evidence_ref": REF, "section": "findings"},
    {"tool": "read_contract", "profile_id": "fixture", "tool_name": "lookup", "revision": "b" * 64},
    {
        "tool": "read_source",
        "snapshot_id": "b" * 64,
        "relative_path": "source/server.py",
        "start_line": 107,
        "end_line": 110,
    },
    {"tool": "check_contract", "case_id": ID, "contract_revision": "b" * 64},
    {"tool": "request_reproduction", "approved_case_id": ID, "profile_revision": "b" * 64},
    {
        "tool": "apply_candidate",
        "candidate_id": CANDIDATE,
        "expected_baseline_hash": "b" * 64,
        "expected_file_hash": "c" * 64,
        "replacement": 'def lookup_result(count):\n    return {"count": count}\n',
        "evidence_refs": [REF],
    },
    {
        "tool": "compare_candidate",
        "candidate_id": CANDIDATE,
        "expected_candidate_tree_hash": "d" * 64,
        "evidence_refs": [REF],
    },
]
PERMISSIONS = {
    "diagnosis": {0, 1, 2, 3, 4},
    "repair": {0, 1, 2, 5},
    "verification": {0, 1, 2, 3, 4, 6},
    "single": set(range(7)),
}


def payload(index, **change):
    return {"action": "request_tool", "request": {"request_id": ID, **REQUESTS[index], **change}}


def encoded(value):
    return json.dumps(value).encode()


@pytest.mark.parametrize("role", PERMISSIONS)
@pytest.mark.parametrize("index", range(7))
def test_every_role_tool_pair_is_enforced_before_execution(role, index):
    if index in PERMISSIONS[role]:
        result = decode_role(encoded(payload(index)), role)
        assert result.request.tool == REQUESTS[index]["tool"]
    else:
        with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
            decode_role(encoded(payload(index)), role)


def test_single_has_exactly_three_role_permission_union():
    assert PERMISSIONS["single"] == set.union(
        *(PERMISSIONS[r] for r in ("diagnosis", "repair", "verification"))
    )
    assert TOOL_MODELS[:5] == LEGACY_TOOLS


@pytest.mark.parametrize("index", [5, 6])
@pytest.mark.parametrize(
    "field",
    [
        "path",
        "relative_path",
        "task_id",
        "role",
        "budget",
        "attempt_id",
        "image_id",
        "suite_sha256",
        "oracle_sha256",
        "accepted",
        "candidate_verified",
    ],
)
def test_host_authority_cannot_be_added_to_model_requests(index, field):
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$") as error:
        decode_role(encoded(payload(index, **{field: "PRIVATE_SENTINEL"})), "single")
    assert "PRIVATE_SENTINEL" not in str(error.value)


@pytest.mark.parametrize("index", [5, 6])
@pytest.mark.parametrize(
    "change",
    [
        {"request_id": "../../secret"},
        {"candidate_id": "no-uuid"},
        {"schema_version": True},
        {"schema_version": 2},
        {"evidence_refs": []},
        {"evidence_refs": [REF, REF]},
        {"evidence_refs": [REF] * 33},
    ],
)
def test_mutation_requests_require_typed_identity_and_bounded_unique_evidence(index, change):
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_role(encoded(payload(index, **change)), "single")


@pytest.mark.parametrize("replacement", ["", "x" * 8193, "界" * 2731, "\x00", "\ud800"])
def test_patch_limit_is_utf8_bytes_and_rejects_invalid_text(replacement):
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_role(encoded(payload(5, replacement=replacement)), "single")


def test_patch_at_exact_utf8_limit_is_ephemeral_and_immutable():
    result = decode_role(encoded(payload(5, replacement="界" * 2730 + "ab")), "repair")
    assert isinstance(result.request, ApplyCandidate)
    assert len(result.request.replacement.encode()) == 8192
    with pytest.raises(ValidationError):
        result.request.replacement = "different"
    assert "path" not in result.request.model_dump()


@pytest.mark.parametrize("role", PERMISSIONS)
@pytest.mark.parametrize(
    "disposition", ["accepted", "candidate_verified", "passed", "proposal_only"]
)
def test_no_role_can_return_a_host_verdict(role, disposition):
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_role(
            encoded(
                {
                    "action": "conclude",
                    "disposition": disposition,
                    "reason_code": "contract_mismatch",
                    "evidence_refs": [REF],
                }
            ),
            role,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_refs": []},
        {"evidence_refs": [REF, REF]},
        {"reason_code": "PRIVATE_SENTINEL"},
        {"next_role": "repair"},
        {"outcome": "candidate_verified"},
        {"accepted": True},
    ],
)
def test_handoff_requires_evidence_and_cannot_select_control_flow(change):
    value = {
        "action": "conclude",
        "disposition": "handoff",
        "reason_code": "contract_mismatch",
        "evidence_refs": [REF],
        **change,
    }
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_role(encoded(value), "single")


@pytest.mark.parametrize(
    "raw",
    [
        b'{"action":"conclude","action":"conclude"}',
        b'{"action":NaN}',
        b'{"action":1e999}',
        b"\xff",
        b"[]",
        b"[" * 22 + b"0" + b"]" * 22,
    ],
)
def test_shared_strict_decoder_is_used(raw):
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_role(raw, "single")


def test_message_byte_limit_and_unknown_role():
    with pytest.raises(PolicyError, match="^MESSAGE_LIMIT_EXCEEDED$"):
        decode_role(b" " * 65537, "single")
    with pytest.raises(PolicyError, match="^UNKNOWN_ROLE$"):
        decode_role(b"{}", "invented")


@pytest.mark.parametrize("role", ["diagnosis", "repair", "verification"])
@pytest.mark.parametrize("index", [5, 6])
def test_legacy_decoder_never_acquires_new_mutation_tools(role, index):
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_legacy(encoded(payload(index)), role)


def test_legacy_and_p006_conclusions_are_not_interchangeable():
    legacy = {
        "action": "conclude",
        "assessment": "hypothesis",
        "reason_code": "contract_mismatch",
        "evidence_refs": [REF],
    }
    assert decode_legacy(encoded(legacy), "diagnosis").assessment == "hypothesis"
    with pytest.raises(PolicyError):
        decode_role(encoded(legacy), "diagnosis")
    current = {
        "action": "conclude",
        "disposition": "handoff",
        "reason_code": "contract_mismatch",
        "evidence_refs": [REF],
    }
    assert isinstance(decode_role(encoded(current), "diagnosis"), RoleConclusion)
    with pytest.raises(PolicyError):
        decode_legacy(encoded(current), "diagnosis")


@pytest.mark.parametrize("role", PERMISSIONS)
def test_role_prompt_exists_without_frozen_oracle_inputs(role):
    path = Path(__file__).parents[2] / "src/agent_workbench/agents" / role / "prompts/p006.txt"
    prompt = path.read_text()
    assert "P0-06 prompt version 1" in prompt
    assert "untrusted data" in prompt
    assert "needs_evidence" in prompt
    for private_detail in ("valid_zero", "valid_negative", "count=2", "id=-1", "oracle.py"):
        assert private_detail not in prompt
