"""HTTP read boundaries with real SQLite and fixed verified snapshots."""

import asyncio
import json
import os
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent_workbench.api import create_app
from agent_workbench.repair_reader import api
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_repair_reader import completed as completed


@pytest.fixture
def client(completed, monkeypatch):
    monkeypatch.setenv("AWB_STATE_DIR", str(completed.store.directory))
    monkeypatch.setattr(api, "ROOT", completed.image)
    with TestClient(create_app(), base_url="http://127.0.0.1:8030") as value:
        yield value


def test_actual_api_routes_and_safe_headers(client, completed):
    task = completed.task_id
    for path in (
        "",
        f"/{task}",
        f"/{task}/candidates/{completed.candidate_id}/diff",
        f"/{task}/comparisons/{completed.comparison_id}",
    ):
        response = client.get("/api/repairs" + path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.json()["schema_version"] == (2 if path in ("", f"/{task}") else 1)
        assert "claim" not in response.text and str(completed.store.directory) not in response.text
    assert client.post("/api/repairs").status_code == 405


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=51", "limit=-1", "limit=１", "limit=2&limit=3", "root=/private"]
)
def test_invalid_query(client, query):
    assert client.get("/api/repairs?" + query).status_code == 400


@pytest.mark.parametrize(
    "task", ["bad", "ABCDEFAB-ABCD-ABCD-ABCD-ABCDEFABCDEF", "00000000000000000000000000000000"]
)
def test_noncanonical_id(client, task):
    response = client.get(f"/api/repairs/{task}")
    assert response.status_code == 400 and task not in response.text


def test_task_candidate_link_is_enforced(client, completed):
    other = completed.cursor.task.task_id
    assert (
        client.get(f"/api/repairs/{other}/candidates/{completed.candidate_id}/diff").status_code
        == 404
    )
    assert (
        client.get(f"/api/repairs/{other}/comparisons/{completed.comparison_id}").status_code == 404
    )
    assert client.get(f"/api/repairs/{uuid4()}").status_code == 404


def test_current_verdict_removed_and_diff_hidden_after_tamper(client, completed):
    path = completed.snapshots.root / completed.candidate_id / "server.py"
    os.chmod(path, 0o600)
    path.write_text("SECRET_TAMPERED_CONTENT")
    response = client.get(f"/api/repairs/{completed.task_id}")
    assert response.status_code == 200
    record = response.json()["comparisons"][0]
    assert record["verification"] == "unavailable" and record["current_outcome"] is None
    assert "SECRET_TAMPERED" not in response.text
    response = client.get(
        f"/api/repairs/{completed.task_id}/candidates/{completed.candidate_id}/diff"
    )
    assert response.status_code == 409 and response.json() == {"error": "artifact_unavailable"}


def test_response_cap_is_applied_before_send(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_RESPONSE", 100)
    response = client.get("/api/repairs")
    assert response.status_code == 413 and response.json() == {"error": "response_limit"}


def test_loopback_and_origin_enforced(client):
    assert client.get("/api/repairs", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/api/repairs", headers={"origin": "https://evil.example"}).status_code == 403


def test_busy_readers_are_not_queued_unbounded(client):
    client.app.state.repair_reads = asyncio.Semaphore(0)
    response = client.get("/api/repairs")
    assert response.status_code == 429 and response.json() == {"error": "repair_reads_busy"}


def test_cancelled_waiter_keeps_thread_slot_until_completion(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def read(*args):
        started.set()
        assert release.wait(3)
        return api.JSONResponse({"schema_version": 2, "repairs": []})

    monkeypatch.setattr(api, "_read", read)

    async def exercise():
        state = SimpleNamespace(repair_reads=asyncio.Semaphore(1), workers=set())
        request = SimpleNamespace(app=SimpleNamespace(state=state))
        task = asyncio.create_task(api._dispatch(request, "list"))
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        response = await api._dispatch(request, "list")
        assert response.status_code == 429
        assert json.loads(response.body)["error"] == "repair_reads_busy"
        release.set()
        await asyncio.gather(*state.workers)
        assert not state.repair_reads.locked()

    asyncio.run(exercise())


def test_all_get_routes_leave_database_bytes_unchanged(client, completed):
    from hashlib import sha256

    before = sha256(completed.store._base.path.read_bytes()).hexdigest()
    task = completed.task_id
    for path in (
        "",
        f"/{task}",
        f"/{task}/candidates/{completed.candidate_id}/diff",
        f"/{task}/comparisons/{completed.comparison_id}",
    ):
        assert client.get("/api/repairs" + path).status_code == 200
    assert sha256(completed.store._base.path.read_bytes()).hexdigest() == before
