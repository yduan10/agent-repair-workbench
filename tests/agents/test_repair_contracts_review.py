"""Independent B3a adversarial checks; no execution, model calls or persistence."""

import json

import pytest
from jsonschema import Draft202012Validator

from agent_workbench.agents.diagnosis.repair_contracts import ADAPTER as DIAGNOSIS
from agent_workbench.agents.repair.repair_contracts import ADAPTER as REPAIR
from agent_workbench.agents.single.repair_contracts import ADAPTER as SINGLE
from agent_workbench.agents.verification.repair_contracts import ADAPTER as VERIFICATION
from agent_workbench.orchestration.policy import PolicyError
from agent_workbench.repair_contracts.codec import decode_role


def mutation(tool="apply_candidate"):
    request = {
        "request_id": "00000000-0000-0000-0000-000000000001",
        "candidate_id": "00000000-0000-0000-0000-000000000002",
        "tool": tool,
        "evidence_refs": [
            {"evidence_id": "00000000-0000-0000-0000-000000000003", "sha256": "a" * 64}
        ],
    }
    if tool == "apply_candidate":
        request.update(
            expected_baseline_hash="b" * 64,
            expected_file_hash="c" * 64,
            replacement="PRIVATE_PATCH_SENTINEL",
        )
    else:
        request["expected_candidate_tree_hash"] = "d" * 64
    return {"action": "request_tool", "request": request}


@pytest.mark.parametrize(
    ("adapter", "tool", "allowed"),
    [
        (DIAGNOSIS, "apply_candidate", False),
        (DIAGNOSIS, "compare_candidate", False),
        (REPAIR, "apply_candidate", True),
        (REPAIR, "compare_candidate", False),
        (VERIFICATION, "apply_candidate", False),
        (VERIFICATION, "compare_candidate", True),
        (SINGLE, "apply_candidate", True),
        (SINGLE, "compare_candidate", True),
    ],
)
def test_exported_json_schema_keeps_mutation_permissions(adapter, tool, allowed):
    schema = adapter.json_schema()
    Draft202012Validator.check_schema(schema)
    assert Draft202012Validator(schema).is_valid(mutation(tool)) is allowed


def test_same_evidence_id_with_a_different_digest_is_not_two_sources():
    value = mutation()
    value["request"]["evidence_refs"].append(
        {**value["request"]["evidence_refs"][0], "sha256": "f" * 64}
    )
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_role(json.dumps(value).encode(), "single")


def test_whole_decision_repr_does_not_expose_patch():
    decision = decode_role(json.dumps(mutation()).encode(), "repair")
    assert "PRIVATE_PATCH_SENTINEL" not in repr(decision)
    assert "PRIVATE_PATCH_SENTINEL" not in str(decision)


@pytest.mark.parametrize("key", ["accepted", "outcome", "next_role"])
def test_host_authority_cannot_hide_inside_evidence(key):
    value = mutation()
    value["request"]["evidence_refs"][0][key] = "PRIVATE_PATCH_SENTINEL"
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$") as caught:
        decode_role(json.dumps(value).encode(), "repair")
    assert "PRIVATE_PATCH_SENTINEL" not in str(caught.value)


def test_nested_duplicate_key_is_rejected_before_schema_validation():
    encoded = json.dumps(mutation()).replace(
        '"expected_file_hash":', '"expected_file_hash": "' + "e" * 64 + '", "expected_file_hash":'
    )
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode_role(encoded.encode(), "repair")
