import json

import pytest

from agent_workbench.orchestration.codec import decode_role
from agent_workbench.orchestration.policy import PolicyError

REF = {"evidence_id": "00000000-0000-0000-0000-000000000001", "sha256": "a" * 64}


def test_hypothesis_is_typed_and_immutable():
    result = decode_role(
        json.dumps(
            {
                "action": "conclude",
                "assessment": "hypothesis",
                "reason_code": "contract_mismatch",
                "evidence_refs": [REF],
            }
        ).encode(),
        "diagnosis",
    )
    assert result.assessment == "hypothesis"
    with pytest.raises(ValueError):
        result.assessment = "inconclusive"


@pytest.mark.parametrize(
    "change",
    [
        {"assessment": "confirmed"},
        {"evidence_refs": []},
        {"evidence_refs": [REF, REF]},
        {"reason_code": "SECRET"},
        {"schema_version": True},
        {"task_id": "SECRET"},
        {"root_cause": "SECRET"},
    ],
)
def test_diagnosis_rejects_invalid_or_privileged_output(change):
    data = {
        "action": "conclude",
        "assessment": "hypothesis",
        "reason_code": "contract_mismatch",
        "evidence_refs": [REF],
        **change,
    }
    with pytest.raises(PolicyError) as error:
        decode_role(json.dumps(data).encode(), "diagnosis")
    assert str(error.value) == "INVALID_MESSAGE"
    assert "SECRET" not in str(error.value)
