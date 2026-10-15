"""Independent P0-06 integration review: repair cases never expand web admission."""

import asyncio
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent_workbench.analysis_store.fencing import AnalysisFence
from agent_workbench.api import create_app
from agent_workbench.controlled_tools.resources import load_case, load_repair_case
from agent_workbench.orchestration.runtime import AnalysisRuntime
from agent_workbench.run_store.models import StoreError
from agent_workbench.web_analyses.fencing import AnalysisWebFence
from agent_workbench.web_analyses.models import WEB_BUDGET, AnalysisRequest
from agent_workbench.web_analyses.store import WebAnalysisStore


def snapshot(store):
    with sqlite3.connect(store._base.path) as db:
        return tuple(db.iterdump())


@pytest.fixture
def store(tmp_path, monkeypatch):
    directory = tmp_path / "state"
    monkeypatch.setenv("AWB_STATE_DIR", str(directory))
    value = WebAnalysisStore(directory)
    value.initialize()
    yield value
    value.close()


@pytest.mark.parametrize("intent", ["check_only", "diagnose", "propose_repair"])
def test_repair_case_rejected_at_http_before_any_persistent_admission(store, intent):
    before = snapshot(store)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/analysis-runs",
            json={"request_id": str(uuid4()), "case_name": "counter_offset", "intent": intent},
            headers={"origin": "http://127.0.0.1:3010"},
        )
        assert response.status_code == 400
        assert response.json() == {"error": "invalid_request"}
    assert snapshot(store) == before
    assert store.list() == []


@pytest.mark.parametrize("cancel_requested", [False, True])
def test_repair_registry_rejected_before_claim_consumption_and_keeps_entire_database(
    store, monkeypatch, cancel_requested
):
    task_id = str(uuid4())
    registry = load_repair_case("counter_offset", task_id=task_id, budget=WEB_BUDGET)
    runtime = AnalysisRuntime(registry, store, None)
    # Intentionally inconsistent internal plumbing: a legal browser payload paired with
    # repair-only resources. Both summary and evidence match the runtime, so the new
    # case boundary, rather than an earlier summary-integrity check, must refuse it.
    request = AnalysisRequest(
        request_id=task_id, case_name="output_mismatch", intent="propose_repair"
    )
    calls = []
    original_start = store.start_created

    def observed_start(*args, **kwargs):
        calls.append("start_created")
        return original_start(*args, **kwargs)

    async def forbidden_execution():
        calls.append("execution")
        raise AssertionError("web execution must not start")

    monkeypatch.setattr(store, "start_created", observed_start)
    monkeypatch.setattr(runtime, "_run_started", forbidden_execution)
    with AnalysisWebFence(store.directory) as owner:
        with AnalysisFence(store.directory, task_id) as fence:
            admitted = store.admit(
                request,
                runtime.initial_summary(),
                policy_sha256="c" * 64,
                owner=owner,
                fence=fence,
            )
            if cancel_requested:
                assert store.request_cancel(task_id)
            before = snapshot(store)
            raw_before = Path(store._base.path).read_bytes()
            with pytest.raises(StoreError, match="^admission_invalid$"):
                asyncio.run(runtime.run_created(admitted.claim, admitted.saved, fence=fence))
            assert calls == []
            assert snapshot(store) == before
            assert Path(store._base.path).read_bytes() == raw_before
            current = store.get(task_id)
            assert current.summary.summary_revision == 0
            assert current.summary.state.phase == "queued"
            assert current.summary.usage.model_calls == 0
            assert [event.event.kind for event in store.events(task_id)] == ["created"]


@pytest.mark.parametrize("case_name", ["output_mismatch", "passing"])
def test_existing_browser_cases_still_admit_and_finish_without_model(store, case_name):
    task_id = str(uuid4())
    request = AnalysisRequest(request_id=task_id, case_name=case_name, intent="check_only")
    registry = load_case(case_name, task_id=task_id, intent="check_only", budget=WEB_BUDGET)
    runtime = AnalysisRuntime(registry, store, None)
    with AnalysisWebFence(store.directory) as owner:
        with AnalysisFence(store.directory, task_id) as fence:
            admitted = store.admit(
                request,
                runtime.initial_summary(),
                policy_sha256="c" * 64,
                owner=owner,
                fence=fence,
            )
            result = asyncio.run(runtime.run_created(admitted.claim, admitted.saved, fence=fence))
            assert result.summary.state.outcome == "check_complete"
            assert result.summary.usage.model_calls == 0
            assert store.release_safe(owner)
