import json

import pytest

from agent_workbench.orchestration.codec import decode_role
from agent_workbench.orchestration.policy import PolicyError

REF = {"evidence_id": "00000000-0000-0000-0000-000000000001", "sha256": "a" * 64}
EDIT = {"path": "src/tool.py", "base_sha256": "b" * 64, "replacement": "return 1\n"}


def proposal(**changes):
    return json.dumps(
        {
            "action": "conclude",
            "disposition": "proposal_only",
            "evidence_refs": [REF],
            "edits": [EDIT],
            **changes,
        }
    ).encode()


def test_proposal_has_no_applied_or_verified_status():
    result = decode_role(proposal(), "repair")
    assert result.disposition == "proposal_only"
    assert result.edits[0].replacement == "return 1\n"


@pytest.mark.parametrize(
    "change",
    [
        {"edits": []},
        {"evidence_refs": []},
        {"disposition": "candidate_verified"},
        {"edits": [EDIT, EDIT]},
        {"disposition": "cannot_propose"},
        {"edits": [{**EDIT, "path": "../hidden.py"}]},
        {
            "edits": [
                {**EDIT, "replacement": "界" * 8192},
                {**EDIT, "path": "second.py", "replacement": "界" * 8192},
            ]
        },
    ],
)
def test_repair_refuses_invalid_and_unbounded_proposals(change):
    with pytest.raises(PolicyError):
        decode_role(proposal(**change), "repair")
