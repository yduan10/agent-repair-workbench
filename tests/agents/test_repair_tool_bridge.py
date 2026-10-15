"""B3c: actual ledger/snapshots with synthetic host reports; these are not model results."""

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution import compare as compare_module
from agent_workbench.candidate_execution.models import STEPS, OracleReport, OracleStep
from agent_workbench.candidate_execution.oracle import ORACLE_SHA256, SUITE_SHA256
from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.controlled_tools.contracts import Reproduce
from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.orchestration.contracts import Budget, EvidenceRef
from agent_workbench.repair_contracts.tools import ApplyCandidate, CompareCandidate
from agent_workbench.repair_runtime import tools as bridge_module
from agent_workbench.repair_runtime.tools import RepairToolBridge
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairTask
from agent_workbench.repair_store.reproductions import ReproductionStore
from agent_workbench.run_store.models import StoreError


def uid():
    return str(uuid4())


@pytest.fixture
def ctx(tmp_path, monkeypatch, request):
    store = ReproductionStore(tmp_path / "state")
    store.initialize()
    snapshots = SnapshotStore(tmp_path / "snapshots")
    baseline = snapshots.create_baseline(uid())
    task_id = uid()
    budget = Budget(total_tokens=1000, output_tokens=100)
    registry = load_case("output_mismatch", task_id=task_id, intent="propose_repair", budget=budget)
    fence = RepairFence(store.directory, task_id)
    fence.acquire()
    task = RepairTask(
        task_id=task_id,
        baseline=baseline.ref,
        mode=getattr(request, "param", "three_role"),
        started_at=datetime.now(UTC),
        budget=budget,
    )
    cursor = store.create_task(task, fence=fence)
    image = tmp_path / "image"
    source = image / "containers/p0_06"
    source.mkdir(parents=True)
    parts = []
    for name in ("Dockerfile", "supervisor.py", "prepare.py"):
        (source / name).write_bytes(b"synthetic image metadata; never executed\n")
        parts.append(name.encode() + b"\0" + (source / name).read_bytes())
    image_sha = digest(b"\0".join(parts))
    (image / "artifacts").mkdir()
    (image / "artifacts/p0-06-image.json").write_text(
        json.dumps(
            {
                "image_id": "sha256:" + "a" * 64,
                "source_sha256": image_sha,
                "base_digest": (
                    "python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
                ),
            }
        )
    )
    state = SimpleNamespace(
        store=store,
        snapshots=snapshots,
        baseline=baseline,
        registry=registry,
        fence=fence,
        cursor=cursor,
        task_id=task_id,
        image=image,
        image_sha=image_sha,
        remaining=500.0,
        attempts=[],
        candidate_failure=False,
        oracle_hook=None,
    )
    state.bridge = bridge(state)

    async def oracle(snapshot, *, scenario, attempt_id, **kwargs):
        with sqlite3.connect(store._base.path) as conn:
            admitted = conn.execute(
                "SELECT kind FROM repair_execution_identities WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            assert admitted is not None, "an external operation ran before durable admission"
        assert attempt_id not in state.attempts, "an admitted operation was replayed"
        state.attempts.append(attempt_id)
        if state.oracle_hook:
            await state.oracle_hook()
        steps = []
        for name in STEPS:
            code = "ok"
            if name in ("valid_one", "valid_zero", "valid_negative") and scenario == "wrong_type":
                if snapshot.ref.kind == "baseline":
                    code = "count_type"
                elif state.candidate_failure:
                    code = "count_value"
            steps.append(
                OracleStep(name=name, status="passed" if code == "ok" else "failed", code=code)
            )
        return OracleReport(
            attempt_id=attempt_id,
            snapshot_id=snapshot.ref.snapshot_id,
            snapshot_tree_sha256=snapshot.ref.tree_sha256,
            snapshot_file_sha256=snapshot.ref.file_sha256,
            suite_sha256=SUITE_SHA256,
            oracle_sha256=ORACLE_SHA256,
            image_id="sha256:" + "a" * 64,
            image_source_sha256=image_sha,
            scenario=scenario,
            steps=steps,
            status="failed" if any(s.status == "failed" for s in steps) else "passed",
            snapshot_verified_before=True,
            snapshot_verified_after=True,
            cleanup="removed",
        )

    state.oracle = oracle
    monkeypatch.setattr(bridge_module, "run_oracle", oracle)
    monkeypatch.setattr(compare_module, "run_oracle", oracle)
    yield state
    fence.close()
    store.close()


def bridge(ctx):
    return RepairToolBridge(
        store=ctx.store,
        registry=ctx.registry,
        baseline=ctx.baseline,
        snapshots=ctx.snapshots,
        image_root=ctx.image,
        fence=ctx.fence,
        remaining_seconds=lambda: ctx.remaining,
    )


def invoke(ctx, role, request):
    result = asyncio.run(ctx.bridge.execute(role, request, cursor=ctx.cursor))
    ctx.cursor = result.cursor
    return result


def reproduce_request(ctx):
    return Reproduce(
        tool="request_reproduction",
        request_id=uid(),
        approved_case_id=ctx.registry.case_id,
        profile_revision=ctx.registry.profile_revision,
    )


def reproduce(ctx):
    role = "single" if ctx.cursor.task.mode == "single_role" else "diagnosis"
    result = invoke(ctx, role, reproduce_request(ctx))
    assert result.response.payload["status"] == "observed_failure"
    return result


def apply_request(ctx, **overrides):
    value = dict(
        tool="apply_candidate",
        request_id=uid(),
        candidate_id=uid(),
        expected_baseline_hash=ctx.baseline.ref.tree_sha256,
        expected_file_hash=ctx.baseline.ref.file_sha256,
        replacement=(
            "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"
            '    return {"count": count}\n'
        ),
        evidence_refs=(ctx.registry.task_spec().evidence[-1],),
    )
    value.update(overrides)
    return ApplyCandidate(**value)


def apply(ctx):
    role = "single" if ctx.cursor.task.mode == "single_role" else "repair"
    result = invoke(ctx, role, apply_request(ctx))
    assert result.response.payload["status"] == "committed"
    return result


def compare_request(ctx, candidate):
    return CompareCandidate(
        tool="compare_candidate",
        request_id=uid(),
        candidate_id=candidate.response.payload["candidate_id"],
        expected_candidate_tree_hash=candidate.response.payload["candidate_tree_hash"],
        evidence_refs=candidate.response.evidence_refs,
    )


def table_count(ctx, table):
    with sqlite3.connect(ctx.store._base.path) as conn:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


@pytest.mark.parametrize("ctx", ["three_role", "single_role"], indirect=True)
def test_full_tool_bridge_is_durable_and_candidate_pass_is_host_derived(ctx):
    reproduce(ctx)
    candidate = apply(ctx)
    result = invoke(
        ctx,
        "single" if ctx.cursor.task.mode == "single_role" else "verification",
        compare_request(ctx, candidate),
    )
    assert result.response.payload["status"] == "candidate_verified"
    assert result.response.payload["accepted"] is False
    assert result.cursor.task.outcome == "candidate_verified"
    assert result.cursor.task.usage.tool_calls == 3
    assert len(ctx.attempts) == 5
    assert table_count(ctx, "repair_comparison_attempts") == 4
    record = ctx.store.comparisons(ctx.task_id)[0]
    assert len(record.results) == 4
    assert {i.status for i in ctx.store.admitted_attempts(ctx.task_id, record.plan.request_id)} == {
        "reported"
    }
    text = canonical(result.response.model_dump(mode="json")).decode()
    for hidden in [
        "valid_zero",
        "valid_negative",
        "invalid_type",
        "initialize",
        "steps",
        "source/server.py",
        "oracle.py",
    ]:
        assert hidden not in text


def test_synthetic_initial_failure_cannot_authorize_patch(ctx):
    result = invoke(ctx, "repair", apply_request(ctx))
    assert result.response.error_code == "PERMISSION_DENIED"
    assert ctx.cursor.task.candidate_count == 0
    assert table_count(ctx, "repair_candidates") == 0


def test_rebuilt_bridge_cannot_inherit_actual_reproduction_authorization(ctx):
    request = reproduce_request(ctx)
    done = invoke(ctx, "diagnosis", request)
    assert done.response.status == "ok"
    ctx.bridge = bridge(ctx)
    replay = invoke(ctx, "diagnosis", request)
    assert replay.replayed and len(ctx.attempts) == 1
    assert invoke(ctx, "repair", apply_request(ctx)).response.error_code == "PERMISSION_DENIED"


@pytest.mark.parametrize("stage", ["reproduction", "apply", "compare"])
def test_exact_repeat_is_read_only_no_new_execution_or_charge(ctx, stage):
    if stage == "reproduction":
        role, request = "diagnosis", reproduce_request(ctx)
    else:
        reproduce(ctx)
        if stage == "apply":
            role, request = "repair", apply_request(ctx)
        else:
            role, request = "verification", compare_request(ctx, apply(ctx))
    original = invoke(ctx, role, request)
    count, revision, attempts = (
        ctx.cursor.task.usage.tool_calls,
        ctx.cursor.task.revision,
        list(ctx.attempts),
    )
    replay = invoke(ctx, role, request)
    assert replay.replayed
    assert replay.response.payload == original.response.payload
    assert ctx.cursor.task.revision == revision and ctx.cursor.task.usage.tool_calls == count
    assert ctx.attempts == attempts


def test_same_request_changed_refs_is_rejected_within_session(ctx):
    reproduce(ctx)
    request = apply_request(ctx)
    invoke(ctx, "repair", request)
    ref = ctx.registry.register(
        {"summary": {"test": "another authorized ref"}, "findings": [], "events": []}
    )
    changed = request.model_copy(update={"evidence_refs": (ref,)})
    result = invoke(ctx, "repair", changed)
    assert result.response.error_code == "REQUEST_CONFLICT"
    assert ctx.cursor.task.candidate_count == 1


@pytest.mark.parametrize("role", ["diagnosis", "verification"])
def test_role_cannot_apply_even_if_request_is_constructed_directly(ctx, role):
    reproduce(ctx)
    result = invoke(ctx, role, apply_request(ctx))
    assert result.response.error_code == "PERMISSION_DENIED"
    assert ctx.cursor.task.candidate_count == 0


def test_foreign_evidence_is_rejected_before_claim(ctx):
    reproduce(ctx)
    result = invoke(
        ctx,
        "repair",
        apply_request(ctx, evidence_refs=(EvidenceRef(evidence_id=uid(), sha256="a" * 64),)),
    )
    assert result.response.error_code == "PERMISSION_DENIED"
    assert table_count(ctx, "repair_candidates") == 0


def test_two_failed_applications_consume_both_candidate_slots(ctx):
    reproduce(ctx)
    for _ in range(2):
        result = invoke(
            ctx, "repair", apply_request(ctx, replacement="def changed():\n    return 1\n")
        )
        assert result.response.error_code == "TOOL_FAILURE"
    assert ctx.cursor.task.candidate_count == 2
    assert invoke(ctx, "repair", apply_request(ctx)).response.error_code == "BUDGET_EXCEEDED"
    assert len(ctx.store.candidates(ctx.task_id)) == 2


def test_new_request_cannot_compare_same_candidate_again(ctx):
    reproduce(ctx)
    candidate = apply(ctx)
    ctx.candidate_failure = True
    failed = invoke(ctx, "verification", compare_request(ctx, candidate))
    assert failed.response.payload["status"] == "rejected"
    assert failed.cursor.task.phase == "ready"
    retry = invoke(ctx, "verification", compare_request(ctx, candidate))
    assert retry.response.error_code == "REQUEST_CONFLICT"
    assert len(ctx.attempts) == 5


def test_second_candidate_after_rejection_starts_from_original_baseline(ctx):
    reproduce(ctx)
    first = apply(ctx)
    ctx.candidate_failure = True
    rejected = invoke(ctx, "verification", compare_request(ctx, first))
    assert rejected.response.payload["rule_failures"] == {"count_value": 3}
    ctx.candidate_failure = False
    second = apply(ctx)
    done = invoke(ctx, "verification", compare_request(ctx, second))
    assert done.cursor.task.outcome == "candidate_verified"
    assert done.cursor.task.candidate_count == 2
    assert len(ctx.attempts) == 9
    assert {x.snapshot.baseline_id for x in ctx.store.candidates(ctx.task_id)} == {
        ctx.baseline.ref.snapshot_id
    }


@pytest.mark.parametrize("remaining", [0, 20, float("nan"), float("inf")])
def test_deadline_reserves_cleanup_before_admission(ctx, remaining):
    ctx.remaining = remaining
    result = invoke(ctx, "diagnosis", reproduce_request(ctx))
    assert result.response.error_code == "BUDGET_EXCEEDED"
    assert not ctx.attempts and ctx.cursor.task.usage.tool_calls == 0


def test_db_failure_prevents_external_execution(ctx):
    with sqlite3.connect(ctx.store._base.path) as conn:
        conn.execute(
            "CREATE TRIGGER refuse_event BEFORE INSERT ON repair_events "
            "BEGIN SELECT RAISE(ABORT,'test'); END"
        )
    result = invoke(ctx, "diagnosis", reproduce_request(ctx))
    assert result.response.error_code == "TOOL_FAILURE"
    assert not ctx.attempts
    assert table_count(ctx, "repair_reproductions") == 0


def test_unsaved_oracle_report_is_pending_unknown_never_retried(ctx, monkeypatch):
    monkeypatch.setattr(
        ctx.store,
        "finish_reproduction",
        lambda *a, **k: (_ for _ in ()).throw(StoreError("store_busy")),
    )
    result = invoke(ctx, "diagnosis", reproduce_request(ctx))
    assert result.requires_reconcile and result.response.error_code == "RESULT_UNKNOWN"
    assert ctx.store.get(ctx.task_id).task.phase == "tool_pending"
    assert len(ctx.attempts) == 1
    with pytest.raises(ResourceError):
        invoke(ctx, "diagnosis", reproduce_request(ctx))


def test_partial_comparison_save_failure_stops_remaining_containers(ctx, monkeypatch):
    reproduce(ctx)
    candidate = apply(ctx)
    original = ctx.store.save_slot

    def fail_second(*args, **kwargs):
        if len(ctx.store.comparisons(ctx.task_id)[0].results) == 1:
            raise StoreError("store_busy")
        return original(*args, **kwargs)

    monkeypatch.setattr(ctx.store, "save_slot", fail_second)
    result = invoke(ctx, "verification", compare_request(ctx, candidate))
    assert result.requires_reconcile
    assert len(ctx.attempts) == 3  # T05 plus two T07 slots; no third comparison execution.
    assert len(ctx.store.comparisons(ctx.task_id)[0].results) == 1
    assert ctx.cursor.task.phase == "comparing"


def test_uncertain_filesystem_publish_is_terminal_unknown(ctx, monkeypatch):
    reproduce(ctx)
    monkeypatch.setattr(
        ctx.snapshots,
        "create_candidate",
        lambda *a: (_ for _ in ()).throw(CandidateError("SNAPSHOT_COMMIT_UNKNOWN")),
    )
    result = invoke(ctx, "repair", apply_request(ctx))
    assert result.cursor.task.outcome == "outcome_unknown"
    assert result.cursor.candidate.status == "outcome_unknown"
    assert result.response.error_code == "RESULT_UNKNOWN"


def test_post_reproduction_baseline_tamper_blocks_application(ctx):
    reproduce(ctx)
    path = ctx.baseline.root / "server.py"
    path.chmod(0o644)
    path.write_text("changed")
    result = invoke(ctx, "repair", apply_request(ctx))
    assert result.response.error_code == "ARTIFACT_MISMATCH"
    assert ctx.store.get(ctx.task_id).task.candidate_count == 0


def test_readonly_tools_reuse_authorization_and_charge_once(ctx):
    for request in ctx.registry.templates("repair"):
        if request.tool not in ("read_contract", "read_source"):
            continue
        result = invoke(ctx, "repair", request)
        assert result.response.status == "ok"
        usage = result.cursor.task.usage.tool_calls
        replay = invoke(ctx, "repair", request)
        assert replay.replayed and replay.cursor.task.usage.tool_calls == usage
        assert replay.response == result.response


def test_stale_cas_does_not_dispatch_an_operation(ctx):
    old = ctx.cursor
    reproduce(ctx)
    ctx.cursor = old
    result = invoke(ctx, "repair", apply_request(ctx))
    assert result.response.error_code in ("REQUEST_CONFLICT", "TOOL_FAILURE")
    assert len(ctx.attempts) == 1
    assert not ctx.store.candidates(ctx.task_id)


def test_native_repeated_cancel_joins_owned_operation_and_blocks_replay(ctx):
    cleaned = []

    async def slow():
        try:
            await asyncio.sleep(30)
        finally:
            cleaned.append(True)

    ctx.oracle_hook = slow

    async def run():
        task = asyncio.create_task(
            ctx.bridge.execute("diagnosis", reproduce_request(ctx), cursor=ctx.cursor)
        )
        while not ctx.attempts:
            await asyncio.sleep(0.001)
        task.cancel()
        task.cancel()
        result = await task
        assert result.cancelled and result.requires_reconcile
        assert cleaned == [True]
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())


def test_missing_prepared_image_is_safe_failure_before_admission(ctx):
    (ctx.image / "artifacts/p0-06-image.json").unlink()
    result = invoke(ctx, "diagnosis", reproduce_request(ctx))
    assert result.response.error_code == "TOOL_FAILURE"
    assert not ctx.attempts


def test_unexpected_apply_io_error_preserves_pending_for_reconciliation(ctx, monkeypatch):
    reproduce(ctx)

    def fail(*args):
        raise OSError("PRIVATE_PATH_SENTINEL")

    monkeypatch.setattr(ctx.snapshots, "create_candidate", fail)
    result = invoke(ctx, "repair", apply_request(ctx))
    assert result.requires_reconcile and result.response.error_code == "RESULT_UNKNOWN"
    assert "PRIVATE_PATH_SENTINEL" not in result.response.model_dump_json()
    assert ctx.store.candidates(ctx.task_id)[0].status == "preparing"


def test_comparison_native_cancel_does_not_leave_worker_and_requires_reconciliation(ctx):
    reproduce(ctx)
    candidate = apply(ctx)
    cleaned = []

    async def slow():
        try:
            await asyncio.sleep(30)
        finally:
            cleaned.append(True)

    ctx.oracle_hook = slow

    async def run():
        task = asyncio.create_task(
            ctx.bridge.execute("verification", compare_request(ctx, candidate), cursor=ctx.cursor)
        )
        while len(ctx.attempts) < 2:
            await asyncio.sleep(0.001)
        task.cancel()
        task.cancel()
        result = await task
        assert result.cancelled and result.requires_reconcile
        assert cleaned == [True]
        assert len(asyncio.all_tasks()) == 1
        assert ctx.store.get(ctx.task_id).task.phase == "comparing"

    asyncio.run(run())


def test_actual_baseline_without_expected_failure_cannot_authorize_patch(ctx, monkeypatch):
    original = ctx.oracle

    async def no_failure(snapshot, **kwargs):
        report = await original(snapshot, **kwargs)
        for step in report.steps:
            step.status, step.code = "passed", "ok"
        report.status = "passed"
        return report

    monkeypatch.setattr(bridge_module, "run_oracle", no_failure)
    result = invoke(ctx, "diagnosis", reproduce_request(ctx))
    assert result.cursor.task.outcome == "inconclusive"
    assert result.response.error_code == "TOOL_FAILURE"
    assert invoke(ctx, "repair", apply_request(ctx)).response.error_code == "PERMISSION_DENIED"
    assert not ctx.store.candidates(ctx.task_id)


def test_bridge_rejects_concurrent_execute_without_starting_second_operation(ctx):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        async def wait():
            entered.set()
            await release.wait()

        ctx.oracle_hook = wait
        task = asyncio.create_task(
            ctx.bridge.execute("diagnosis", reproduce_request(ctx), cursor=ctx.cursor)
        )
        await entered.wait()
        with pytest.raises(ResourceError, match="PERMISSION_DENIED"):
            await ctx.bridge.execute("diagnosis", reproduce_request(ctx), cursor=ctx.cursor)
        release.set()
        result = await task
        assert result.response.status == "ok"
        assert len(ctx.attempts) == 1

    asyncio.run(run())
