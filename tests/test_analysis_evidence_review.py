"""Independent readable-evidence API boundaries; temporary state only."""

import asyncio
import sqlite3
import threading
from types import SimpleNamespace

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from agent_workbench.analysis_store import api
from agent_workbench.analysis_store.evidence import resolve_evidence
from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.api import create_app
from tests.test_analysis_evidence import persist, uid

pytest_plugins = ("tests.test_analysis_evidence",)


def test_only_saved_subset_is_returned_not_all_reconstructible_content(sample):
    root, summary = sample
    one = summary.model_copy(update={"evidence_refs": (summary.evidence_refs[1],)})
    response = resolve_evidence(one, "a" * 64, root=root)
    assert len(response.evidence) == 1
    assert response.evidence[0].kind == "source"
    assert response.evidence[0].schemas is None and response.evidence[0].report is None


def test_corrupt_task_ledger_cannot_produce_readable_evidence(sample, tmp_path, monkeypatch):
    _, summary = sample
    store = AnalysisStore(tmp_path / "state")
    store.initialize()
    persist(store, summary)
    with sqlite3.connect(store._base.path) as connection:
        connection.execute("UPDATE analysis_events SET sha256=?", ("0" * 64,))
    monkeypatch.setenv("AWB_STATE_DIR", str(store.directory))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.get(f"/api/analyses/{summary.task_id}/evidence")
    assert response.status_code == 503
    assert response.json() == {"error": "analysis_corrupt"}
    assert "lookup_result" not in response.text
    store.close()


def test_read_missing_evidence_does_not_initialize_store(tmp_path, monkeypatch):
    directory = tmp_path / "absent-state"
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.get(f"/api/analyses/{uid()}/evidence")
    assert response.status_code == 404
    assert not directory.exists()


def test_cancelled_http_waiter_does_not_release_active_checker_slot(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return JSONResponse({"done": True})

    monkeypatch.setattr(api, "_read", blocked)

    async def run():
        app = SimpleNamespace(state=SimpleNamespace(gate=asyncio.Semaphore(1), workers=set()))
        request = SimpleNamespace(app=app)
        waiting = asyncio.create_task(api.evidence(uid(), request))
        try:
            while not entered.is_set():
                await asyncio.sleep(0.001)
            waiting.cancel()
            try:
                await waiting
            except asyncio.CancelledError:
                pass
            assert app.state.gate.locked()
            second = await api.evidence(uid(), request)
            assert second.status_code == 429
            release.set()
            await asyncio.gather(*tuple(app.state.workers))
            assert not app.state.gate.locked()
        finally:
            release.set()

    asyncio.run(run())
