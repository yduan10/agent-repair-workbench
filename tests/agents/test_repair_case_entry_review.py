"""Independent H3 counterexamples; real temporary SQLite, no model provider or Docker."""

import asyncio
import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.cli import main
from agent_workbench.controlled_tools.resources import load_repair_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_cases.profiles import get_profile
from agent_workbench.repair_runtime.controller import RepairController
from tests.agents.test_repair_cli import configured as configured
from tests.agents.test_repair_controller import Scripted
from tests.agents.test_repair_tool_bridge import ctx as ctx


def ledger_rows(ctx):
    with sqlite3.connect(ctx.store._base.path) as db:
        return tuple(
            db.execute("SELECT payload FROM " + table + " ORDER BY rowid").fetchall()
            for table in ("repair_tasks", "repair_requests", "repair_events")
        )


@pytest.mark.parametrize("case_id", ["output_mismatch", "counter_offset"])
@pytest.mark.parametrize(
    "flag,value",
    [
        ("--output-tokens", "8193"),
        ("--model-calls", "13"),
        ("--tool-calls", "21"),
        ("--candidates", "3"),
        ("--timeout", "601"),
        ("--total-tokens", "0"),
    ],
)
def test_case_selection_never_expands_budget(ctx, configured, capsys, case_id, flag, value):
    before = ledger_rows(ctx)
    assert main(["repair", "--case", case_id, flag, value]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "INVALID_CONFIGURATION"}
    assert configured == [] and ctx.attempts == [] and ledger_rows(ctx) == before
    assert not (ctx.store.directory / "repair-snapshots").exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--root", "/private/input"],
        ["--manifest", "/private/manifest"],
        ["--scenario", "pass"],
        ["--resume", "private-task"],
    ],
)
def test_new_case_does_not_grant_external_sources_or_resume(ctx, configured, capsys, extra):
    before = ledger_rows(ctx)
    with pytest.raises(SystemExit) as error:
        main(["repair", "--case", "counter_offset", *extra])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert output.err == "invalid_arguments\n" and output.out == ""
    assert not configured and not ctx.attempts and ledger_rows(ctx) == before


@pytest.mark.parametrize("case_id", ["output_mismatch", "counter_offset"])
@pytest.mark.parametrize("mutation", ["registry_source", "baseline_manifest", "intent"])
def test_controller_rejects_forged_bindings_before_task_creation(ctx, case_id, mutation):
    other = get_profile("counter_offset" if case_id == "output_mismatch" else "output_mismatch")
    baseline = ctx.snapshots.create_baseline(str(uuid4()), case_id=case_id)
    registry = load_repair_case(
        case_id,
        task_id=str(uuid4()),
        budget=Budget(total_tokens=2000000, output_tokens=8192),
    )
    if mutation == "registry_source":
        registry._source = registry._source.model_copy(update={"sha256": other.source_sha256})
    elif mutation == "baseline_manifest":
        baseline = replace(
            baseline,
            ref=baseline.ref.model_copy(
                update={"manifest_sha256": other.manifest_sha256},
            ),
        )
    else:
        registry._original = registry._original.model_copy(update={"intent": "diagnose"})
    adapter = Scripted(ctx, [])
    runtime = RepairController(
        store=ctx.store,
        snapshots=ctx.snapshots,
        baseline=baseline,
        registry=registry,
        adapter=adapter,
        mode="three_role",
        image_root=ctx.image,
    )
    before = ledger_rows(ctx)
    with pytest.raises((CandidateError, ResourceError)):
        asyncio.run(runtime.run())
    assert adapter.calls == 0 and adapter.prepared == [] and not ctx.attempts
    assert ledger_rows(ctx) == before
