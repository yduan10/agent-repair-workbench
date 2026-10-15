"""Real temporary AnalysisStore + public fixture reconstruction, no model or Docker."""

import shutil
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_workbench.analysis_store.evidence import EvidenceResponse, resolve_evidence
from agent_workbench.analysis_store.fencing import AnalysisFence
from agent_workbench.analysis_store.models import AnalysisEvent
from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.api import create_app
from agent_workbench.controlled_tools.contracts import ReadSource
from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.mcp_config import ROOT
from agent_workbench.orchestration.contracts import (
    AnalysisSummary,
    Budget,
    EvidenceRef,
    TaskState,
    Usage,
)


def uid():
    return str(uuid4())


@pytest.fixture
def sample(tmp_path):
    root = tmp_path / "public"
    shutil.copytree(ROOT / "examples/analysis", root)
    task_id = uid()
    budget = Budget(total_tokens=1000, output_tokens=100)
    registry = load_case(
        "output_mismatch", task_id=task_id, intent="check_only", budget=budget, root=root
    )
    source_request = next(x for x in registry.templates("diagnosis") if isinstance(x, ReadSource))
    source = registry.source(source_request)
    registry.register(
        {"summary": {k: v for k, v in source.items() if k != "text"}, "findings": [], "events": []}
    )
    registry.register(
        {
            "summary": {"tool": "lookup", "contract_revision": registry.contract_revision},
            "findings": [],
            "events": [],
        }
    )
    summary = AnalysisSummary(
        task_id=task_id,
        source_kind="synthetic",
        state=TaskState(task_id=task_id, intent="check_only"),
        started_at=datetime.now(UTC),
        budget=budget,
        usage=Usage(),
        evidence_refs=registry.task_spec().evidence,
    )
    return root, summary


def test_precise_hash_reconstruction_has_readable_content_and_no_call_values(sample):
    root, summary = sample
    result = resolve_evidence(summary, "a" * 64, root=root)
    assert [x.kind for x in result.evidence] == ["report", "source", "contract"]
    report, source, contract = result.evidence
    assert report.report.status == "failed" and report.report.output == "failed"
    assert [(f.code, f.path) for f in report.findings] == [
        ("output_schema_violation", "/result/structured_content/count")
    ]
    assert source.source.start_line == 107 and source.source.end_line == 110
    assert "def lookup_result" in source.source.text
    assert contract.schemas.output_schema["properties"]["count"]["type"] == "integer"
    raw = result.model_dump_json()
    assert '"arguments"' not in raw and '"structured_content":' not in raw
    assert EvidenceResponse.model_validate_json(raw) == result


@pytest.mark.parametrize("mutation", ["source", "manifest", "envelope", "symlink"])
def test_tampered_resources_never_expose_content(sample, tmp_path, mutation):
    root, summary = sample
    target = (
        root
        / {
            "source": "source/server.py",
            "manifest": "manifest.json",
            "envelope": "output_mismatch.json",
            "symlink": "source/server.py",
        }[mutation]
    )
    if mutation == "symlink":
        other = tmp_path / "private.txt"
        other.write_text("PRIVATE_SENTINEL")
        target.unlink()
        target.symlink_to(other)
    else:
        target.write_text("PRIVATE_SENTINEL")
    result = resolve_evidence(summary, "a" * 64, root=root)
    assert (
        result.evidence[1].kind == "unavailable"
        if mutation != "envelope"
        else result.evidence[0].kind == "unavailable"
    )
    assert "PRIVATE_SENTINEL" not in result.model_dump_json()
    assert all(item.source is None for item in result.evidence if item.kind == "unavailable")


@pytest.mark.parametrize("change", ["hash", "source_kind"])
def test_unknown_hash_or_non_fixture_source_is_explicitly_unavailable(sample, change):
    root, summary = sample
    if change == "hash":
        summary = summary.model_copy(
            update={"evidence_refs": (EvidenceRef(evidence_id=uid(), sha256="0" * 64),)}
        )
    else:
        summary = summary.model_copy(update={"source_kind": "public_historical"})
    result = resolve_evidence(summary, "a" * 64, root=root)
    assert all(item.kind == "unavailable" for item in result.evidence)
    assert all(
        item.description == "仅保留引用，具体内容未保存或当前版本不匹配" for item in result.evidence
    )


def persist(store, summary):
    with AnalysisFence(store.directory, summary.task_id) as fence:
        return store.create(summary, AnalysisEvent(kind="created"), fence=fence)


def test_api_reads_real_store_and_never_accepts_foreign_reference(sample, tmp_path, monkeypatch):
    _, summary = sample
    store = AnalysisStore(tmp_path / "state")
    store.initialize()
    saved = persist(store, summary)
    other_id = uid()
    other_ref = EvidenceRef(evidence_id=uid(), sha256="0" * 64)
    other = summary.model_copy(
        update={
            "task_id": other_id,
            "state": TaskState(task_id=other_id, intent="check_only"),
            "evidence_refs": (other_ref,),
        }
    )
    persist(store, other)
    before = store.detail(summary.task_id)
    monkeypatch.setenv("AWB_STATE_DIR", str(store.directory))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.get(
            f"/api/analyses/{summary.task_id}/evidence?evidence_id={other_ref.evidence_id}"
        )
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        payload = EvidenceResponse.model_validate_json(response.content)
        assert payload.summary_sha256 == saved.sha256
        assert tuple(x.ref for x in payload.evidence) == summary.evidence_refs
        assert other_ref.evidence_id not in response.text
        assert (
            client.get(f"/api/analyses/{other_id}/evidence").json()["evidence"][0]["kind"]
            == "unavailable"
        )
        assert client.get(f"/api/analyses/{uid()}/evidence").status_code == 404
        assert client.get("/api/analyses/no-uuid/evidence").status_code == 400
        assert (
            client.get(
                f"/api/analyses/{summary.task_id}/evidence", headers={"origin": "https://evil.test"}
            ).status_code
            == 403
        )
        assert client.post(f"/api/analyses/{summary.task_id}/evidence").status_code == 405
        assert set(client.get(f"/api/analyses/{summary.task_id}").json()) == {
            "summary",
            "sha256",
            "events",
        }
    assert store.detail(summary.task_id) == before
    store.close()


def test_strict_response_rejects_extra_fields(sample):
    root, summary = sample
    response = resolve_evidence(summary, "a" * 64, root=root).model_dump(mode="json")
    response["evidence"][0]["raw_result"] = "private"
    with pytest.raises(ValidationError):
        EvidenceResponse.model_validate(response)


def test_evidence_reconstruction_respects_shared_checker_slot(tmp_path, monkeypatch):
    monkeypatch.setenv("AWB_STATE_DIR", str(tmp_path / "missing"))
    app = create_app()
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.portal.call(app.state.gate.acquire)
        try:
            response = client.get(f"/api/analyses/{uid()}/evidence")
            assert response.status_code == 429
            assert response.json() == {"error": "evidence_busy"}
        finally:
            client.portal.call(app.state.gate.release)
    assert not (tmp_path / "missing").exists()
