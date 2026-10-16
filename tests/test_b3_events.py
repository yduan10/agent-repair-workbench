"""Public events are a bounded, audited projection, not private request records."""

from uuid import uuid4

from fastapi.testclient import TestClient

from agent_workbench import api
from tests.test_web_repair_api import ctx as ctx
from tests.test_web_repair_api import host as host
from tests.test_web_repair_api import request


def test_events_project_private_records_and_bind_web_receipt(host):
    with TestClient(api.app, base_url="http://127.0.0.1:8030") as client:
        payload = request()
        response = client.post(
            "/api/repair-runs", json=payload, headers={"origin": "http://127.0.0.1:3010"}
        )
        assert response.status_code == 202
        response = client.get(f"/api/repair-runs/{payload['request_id']}/events")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == data["revision"] + 1
        assert data["task_id"] == payload["request_id"]
        for event in data["events"]:
            assert set(event) == {
                "revision",
                "at",
                "kind",
                "role",
                "operation",
                "tool",
                "status",
                "error_code",
            }
        assert "claim" not in response.text and "payload_sha256" not in response.text
        assert client.get(f"/api/repair-runs/{uuid4()}/events").status_code == 404
        assert (
            client.get(f"/api/repair-runs/{payload['request_id']}/events?raw=true").status_code
            == 400
        )
        assert client.get("/api/repair-runs/invalid/events").status_code == 400
