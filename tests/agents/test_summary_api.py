import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter

from agent_workbench.api import create_app
from agent_workbench.orchestration.codec import decode
from agent_workbench.orchestration.contracts import AnalysisSummary, Budget, TaskState, Usage
from agent_workbench.orchestration.policy import PolicyError

ID = "00000000-0000-0000-0000-000000000001"


def summary():
    return AnalysisSummary(
        task_id=ID,
        source_kind="synthetic",
        state=TaskState(task_id=ID, intent="diagnose"),
        started_at=datetime(2026, 10, 13, tzinfo=UTC),
        budget=Budget(total_tokens=1000, output_tokens=100),
        usage=Usage(),
        evidence_refs=(),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"task_id": ID[:-1] + "2"},
        {"summary_revision": 1},
        {"finished_at": "2026-10-13T00:00:00Z"},
        {"started_at": "2026-10-13T00:00:00+08:00"},
        {"source_kind": "private"},
        {"raw_response": "SECRET"},
        {"model_config_sha256": "a" * 64},
        {"cost_amount": 0},
        {"usage": {"model_calls": 1, "usage_complete": False}},
        {
            "usage": {"model_calls": 1, "reserved_tokens": 1001, "usage_complete": False},
            "model_config_sha256": "a" * 64,
        },
        {"usage": {"known_input_tokens": 1}},
        {"usage": {"model_calls": 1, "reserved_tokens": 5, "usage_complete": True}},
    ],
)
def test_summary_rejects_inconsistent_and_sensitive_payloads(change):
    payload = summary().model_dump(mode="json") | change
    with pytest.raises(PolicyError) as error:
        decode(json.dumps(payload).encode(), TypeAdapter(AnalysisSummary))
    assert "SECRET" not in str(error.value)


def test_unknown_usage_preserves_reservation_and_separate_revision():
    payload = summary().model_dump(mode="json")
    payload.update(
        summary_revision=3,
        model_config_sha256="a" * 64,
        state={"task_id": ID, "intent": "diagnose", "phase": "diagnosing", "revision": 2},
        usage={
            "model_calls": 1,
            "reserved_tokens": 900,
            "known_input_tokens": 100,
            "usage_complete": False,
        },
    )
    saved = decode(json.dumps(payload).encode(), TypeAdapter(AnalysisSummary))
    assert saved.usage.reserved_tokens == 900 and saved.summary_revision > saved.state.revision
    assert saved.cost_amount is None


def test_catalog_real_api_is_read_only_and_exports_valid_schemas(tmp_path, monkeypatch):
    state_dir = tmp_path / "not-created"
    monkeypatch.setenv("AWB_STATE_DIR", str(state_dir))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.get("/api/agent-contracts")
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        data = response.json()
        assert data["runtime_available"] is False
        assert [x["id"] for x in data["roles"]] == ["diagnosis", "repair", "verification"]
        assert len(data["tools"]) == 5
        for role in data["roles"]:
            Draft202012Validator.check_schema(role["output_schema"])
        for tool in data["tools"]:
            Draft202012Validator.check_schema(tool["request_schema"])
        for key in ("task_schema", "state_schema", "summary_schema"):
            Draft202012Validator.check_schema(data[key])
        assert client.post("/api/agent-contracts", json={}).status_code == 405
        assert (
            client.get("/api/agent-contracts", headers={"Origin": "https://evil.test"}).status_code
            == 403
        )
        assert client.get("/api/agent-contracts", headers={"Host": "evil.test"}).status_code == 400
        assert not state_dir.exists()
