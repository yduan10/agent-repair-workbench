import json

import pytest

from agent_workbench.orchestration.codec import decode_role
from agent_workbench.orchestration.policy import PolicyError

REF = {"evidence_id": "00000000-0000-0000-0000-000000000001", "sha256": "a" * 64}


@pytest.mark.parametrize("assessment,refs", [("needs_evidence", []), ("proposal_reviewed", [REF])])
def test_verifier_can_explain_but_not_certify(assessment, refs):
    result = decode_role(
        json.dumps(
            {
                "action": "conclude",
                "assessment": assessment,
                "reason_code": "proposal_requires_execution",
                "evidence_refs": refs,
            }
        ).encode(),
        "verification",
    )
    assert result.assessment == assessment


@pytest.mark.parametrize(
    "change",
    [
        {"assessment": "candidate_verified"},
        {"accepted": True},
        {"evidence_refs": []},
        {"budget": {"total_tokens": 999999}},
    ],
)
def test_verifier_cannot_claim_success_or_change_budget(change):
    data = {
        "action": "conclude",
        "assessment": "proposal_reviewed",
        "reason_code": "proposal_requires_execution",
        "evidence_refs": [REF],
        **change,
    }
    with pytest.raises(PolicyError):
        decode_role(json.dumps(data).encode(), "verification")
