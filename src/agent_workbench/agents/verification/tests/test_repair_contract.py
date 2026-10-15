"""P0-06 role-local conclusion contract tests; the host retains final authority."""

import json

import pytest

from agent_workbench.agents.verification.repair_contracts import ADAPTER
from agent_workbench.orchestration.codec import decode
from agent_workbench.repair_contracts.common import RoleConclusion


@pytest.mark.parametrize("disposition", ["handoff", "needs_evidence"])
def test_role_can_only_handoff_or_report_missing_evidence(disposition):
    refs = [{"evidence_id": "00000000-0000-0000-0000-000000000001", "sha256": "a" * 64}]
    raw = json.dumps(
        {
            "action": "conclude",
            "disposition": disposition,
            "reason_code": "evidence_missing",
            "evidence_refs": refs if disposition == "handoff" else [],
        }
    ).encode()
    result = decode(raw, ADAPTER)
    assert isinstance(result, RoleConclusion)
    assert result.disposition == disposition
    assert "outcome" not in result.model_dump()
    assert "accepted" not in result.model_dump()
