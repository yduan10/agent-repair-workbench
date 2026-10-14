"""Independent evidence handoff tests; no model, network or user state."""

from dataclasses import replace
from uuid import uuid4

import pytest

from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.orchestration.runtime import AnalysisRuntime


def test_new_role_gets_registered_summary_without_previous_chat_or_raw_events(tmp_path):
    registry = load_case(
        "output_mismatch",
        task_id=str(uuid4()),
        intent="propose_repair",
        budget=Budget(total_tokens=2_000_000, output_tokens=8192),
    )
    ref = registry.register(
        {"summary": {"status": "failed"}, "findings": [], "events": ["PRIVATE_EVENT"]}
    )
    store = AnalysisStore(tmp_path / "state")
    try:
        runtime = AnalysisRuntime(registry, store, None)
        runtime.messages["diagnosis"] = [{"role": "assistant", "content": "PRIVATE_CHAT"}]
        context = runtime.context("verification")
        record = next(
            item
            for item in context["evidence_records"]
            if item["reference"]["evidence_id"] == ref.evidence_id
        )
        assert record == {
            "reference": ref.model_dump(mode="json"),
            "summary": {"status": "failed"},
            "findings": [],
        }
        assert "PRIVATE_CHAT" not in str(context)
        assert "PRIVATE_EVENT" not in str(context)
        original = registry._records[ref.evidence_id]
        registry._records[ref.evidence_id] = replace(original, raw=b"{}")
        with pytest.raises(ResourceError, match="ARTIFACT_MISMATCH"):
            runtime.context("verification")
    finally:
        store.close()
