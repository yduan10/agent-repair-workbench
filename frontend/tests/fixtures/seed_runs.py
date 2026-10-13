"""Create synthetic contract records in an explicitly isolated UI test store, never Docker."""

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Checks, Report
from agent_workbench.run_store import RunStore
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport

state = Path(os.environ["AWB_STATE_DIR"]).resolve()
if (
    os.environ.get("AWB_RUNS_E2E") != "1"
    or state.name != "state"
    or not state.parent.name.startswith("awb-p004-e2e-")
    or state.parent.parent != Path(tempfile.gettempdir()).resolve()
    or state.exists()
):
    raise SystemExit("isolated_empty_test_store_required")
store = RunStore(state)
try:
    store.initialize()
    views = []
    for status in ("queued", "running", "succeeded", "failed", "cancelled", "outcome_unknown"):
        created = store.create("isolated-fixture", "pass", "a" * 64, "b" * 64)
        if status == "queued":
            views.append(created.model_dump(mode="json"))
            continue
        claim = store.claim(created.run_id, created.version)
        if status == "running":
            views.append(claim.run.model_dump(mode="json"))
            continue
        outcome = {
            "succeeded": "completed",
            "failed": "tool_error",
            "cancelled": "transport_error",
            "outcome_unknown": "outcome_unknown",
        }[status]
        report = SandboxReport(
            run_id=claim.run.attempt_id,
            record_id=created.run_id,
            mcp=MCPReport(
                invocation_id=str(uuid4()),
                adapter_outcome=outcome,
                contract_report=Report(
                    status="passed", checks=Checks(input="passed", output="passed")
                )
                if status == "succeeded"
                else None,
            ),
            execution=ExecutionEvidence(
                cleanup="unconfirmed" if status == "outcome_unknown" else "removed"
            ),
        )
        result = store.finish(
            created.run_id,
            claim.run.attempt_id,
            claim.token,
            claim.run.version,
            status,
            report,
            "unavailable" if status == "outcome_unknown" else "absent",
        )
        views.append(result.model_dump(mode="json"))
    print(json.dumps({"runs": views}))
finally:
    store.close()
