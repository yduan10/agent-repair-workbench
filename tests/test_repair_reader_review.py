"""Independent read-only API integrity and bounded-worker counterexamples."""

import asyncio
import json
import threading
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from agent_workbench.api import create_app
from agent_workbench.candidate_execution import compare
from agent_workbench.repair_reader import api
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_repair_read_api import client as client
from tests.test_repair_reader import completed as completed


def test_oracle_version_drift_revokes_live_verdict_without_hiding_history(
    client, completed, monkeypatch
):
    monkeypatch.setattr(compare, "ORACLE_SHA256", "b" * 64)
    response = client.get(f"/api/repairs/{completed.task_id}")
    assert response.status_code == 200
    comparison = response.json()["comparisons"][0]
    assert comparison["recorded_outcome"] == "candidate_verified"
    assert comparison["verification"] == "unavailable"
    assert comparison["current_outcome"] is None and comparison["slots"] == []
    assert comparison["reason"] is None
    # A content diff is still readable; this is not a current repair verdict.
    response = client.get(
        f"/api/repairs/{completed.task_id}/candidates/{completed.candidate_id}/diff"
    )
    assert response.status_code == 200


def test_entire_snapshot_root_symlink_is_refused_even_for_hash_matching_files(
    client, completed, tmp_path
):
    root = completed.snapshots.root
    relocated = tmp_path / "relocated"
    root.rename(relocated)
    root.symlink_to(relocated, target_is_directory=True)
    response = client.get(f"/api/repairs/{completed.task_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"][0]["snapshot_status"] == "unavailable"
    assert body["comparisons"][0]["current_outcome"] is None
    assert str(relocated) not in response.text
    response = client.get(
        f"/api/repairs/{completed.task_id}/candidates/{completed.candidate_id}/diff"
    )
    assert response.status_code == 409
    assert response.json() == {"error": "artifact_unavailable"}


def test_missing_state_all_http_reads_and_shutdown_never_initialize(tmp_path, monkeypatch):
    directory = tmp_path / "not-created"
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    task, candidate, comparison = (str(uuid4()) for _ in range(3))
    with TestClient(create_app(), base_url="http://127.0.0.1:8030") as client:
        assert client.get("/api/repairs").json() == {"schema_version": 2, "repairs": []}
        for path in (
            task,
            f"{task}/candidates/{candidate}/diff",
            f"{task}/comparisons/{comparison}",
        ):
            response = client.get("/api/repairs/" + path)
            assert response.status_code == 404
            assert response.json() == {"error": "repair_record_not_found"}
    assert not directory.exists()


def test_two_cancelled_waiters_do_not_allow_third_worker(monkeypatch):
    entered = [threading.Event(), threading.Event()]
    release = threading.Event()
    mutex = threading.Lock()
    count = 0

    def read(*args):
        nonlocal count
        with mutex:
            index = count
            count += 1
        assert index < 2
        entered[index].set()
        assert release.wait(3)
        return api.JSONResponse({"schema_version": 2, "repairs": []})

    monkeypatch.setattr(api, "_read", read)

    async def exercise():
        state = SimpleNamespace(repair_reads=asyncio.Semaphore(2), workers=set())
        request = SimpleNamespace(app=SimpleNamespace(state=state))
        tasks = [asyncio.create_task(api._dispatch(request, "list")) for _ in range(2)]
        try:
            assert await asyncio.to_thread(entered[0].wait, 2)
            assert await asyncio.to_thread(entered[1].wait, 2)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for _ in range(3):
                response = await api._dispatch(request, "list")
                assert response.status_code == 429
                assert json.loads(response.body) == {"error": "repair_reads_busy"}
            assert count == 2
        finally:
            release.set()
            await asyncio.gather(*state.workers)
        assert not state.repair_reads.locked()
        assert state.repair_reads._value == 2

    asyncio.run(exercise())
