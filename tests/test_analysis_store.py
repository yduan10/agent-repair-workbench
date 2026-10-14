"""B1: real SQLite CAS/event/accounting/ownership. No models or tool dispatch."""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import update

from agent_workbench.analysis_store.fencing import AnalysisFence
from agent_workbench.analysis_store.models import AnalysisEvent
from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.api import create_app
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.orchestration.contracts import (
    AnalysisSummary,
    Budget,
    EvidenceRef,
    TaskState,
    Usage,
)
from agent_workbench.orchestration.policy import transition
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.schema import analysis_events, analysis_summaries
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.models import SandboxConfig


@pytest.fixture
def context(tmp_path):
    store = AnalysisStore(tmp_path / "state")
    store.initialize()
    task_id = str(uuid4())
    summary = AnalysisSummary(
        task_id=task_id,
        source_kind="synthetic",
        state=TaskState(task_id=task_id, intent="diagnose"),
        started_at=datetime.now(UTC),
        budget=Budget(total_tokens=10000, output_tokens=1000),
        usage=Usage(),
        evidence_refs=(EvidenceRef(evidence_id=str(uuid4()), sha256="a" * 64),),
    )
    with AnalysisFence(store.directory, task_id) as fence:
        saved = store.create(summary, AnalysisEvent(kind="created"), fence=fence)
        yield store, fence, saved
    store.close()


def advanced(saved, phase, **changes):
    old = saved.summary
    return old.model_copy(
        update={
            "state": transition(old.state, phase, expected_revision=old.state.revision),
            "summary_revision": old.summary_revision + 1,
            **changes,
        }
    )


def save(store, fence, old, summary, event):
    return store.save(
        summary,
        event,
        expected_revision=old.summary.summary_revision,
        expected_sha256=old.sha256,
        fence=fence,
    )


def checking(context):
    store, fence, initial = context
    return save(
        store, fence, initial, advanced(initial, "checking"), AnalysisEvent(kind="phase_changed")
    )


def started(context):
    store, fence, _ = context
    old = checking(context)
    event = AnalysisEvent(
        kind="model_started",
        role="diagnosis",
        call_id=str(uuid4()),
        request_sha256="b" * 64,
        input_reserved=100,
        output_reserved=50,
        reservation_sha256="c" * 64,
    )
    summary = old.summary.model_copy(
        update={
            "summary_revision": old.summary.summary_revision + 1,
            "usage": Usage(model_calls=1, reserved_tokens=150, usage_complete=False),
            "model_config_sha256": "d" * 64,
        }
    )
    return save(store, fence, old, summary, event), event


def test_cas_idempotent_event_identity_and_atomic_metadata(context):
    store, fence, old = context
    summary, event = advanced(old, "checking"), AnalysisEvent(kind="phase_changed")
    new = save(store, fence, old, summary, event)
    assert not new.reused
    replay = save(store, fence, old, summary, event)
    assert replay.reused and replay.sha256 == new.sha256
    with pytest.raises(StoreError, match="^analysis_conflict$"):
        save(store, fence, old, summary, event.model_copy(update={"error_code": "CANCELLED"}))
    with pytest.raises(StoreError, match="^analysis_conflict$"):
        save(store, fence, old, summary.model_copy(update={"summary_revision": 2}), event)
    assert [e.revision for e in store.events(summary.task_id)] == [0, 1]
    assert (
        digest(canonical(store.get(summary.task_id).summary.model_dump(mode="json"))) == new.sha256
    )
    assert store.list()[0].summary == summary


@pytest.mark.parametrize(
    "change",
    [
        {"budget": Budget(total_tokens=9999, output_tokens=1000)},
        {"source_kind": "public_historical"},
        {"started_at": datetime(2025, 1, 1, tzinfo=UTC)},
        {"evidence_refs": ()},
        {"usage": Usage(tool_calls=1)},
        {"proposal_count": 1},
    ],
)
def test_immutable_fields_and_accounting_reject(context, change):
    store, fence, old = context
    with pytest.raises(StoreError):
        save(
            store,
            fence,
            old,
            advanced(old, "checking", **change),
            AnalysisEvent(kind="phase_changed"),
        )
    assert store.get(old.summary.task_id).sha256 == old.sha256


def test_model_reserve_settle_once_and_unknown_does_not_refund(context):
    store, fence, _ = context
    old, event = started(context)
    settled_event = event.model_copy(
        update={"kind": "model_settled", "known_input_tokens": 10, "known_output_tokens": 5}
    )
    settled = old.summary.model_copy(
        update={
            "summary_revision": old.summary.summary_revision + 1,
            "usage": Usage(model_calls=1, known_input_tokens=10, known_output_tokens=5),
        }
    )
    new = save(store, fence, old, settled, settled_event)
    assert save(store, fence, old, settled, settled_event).reused
    with pytest.raises(StoreError, match="^analysis_call_conflict$"):
        save(
            store,
            fence,
            new,
            settled.model_copy(update={"summary_revision": settled.summary_revision + 1}),
            settled_event,
        )
    next_event = event.model_copy(update={"call_id": str(uuid4())})
    pending = settled.model_copy(
        update={
            "summary_revision": settled.summary_revision + 1,
            "usage": Usage(
                model_calls=2,
                known_input_tokens=10,
                known_output_tokens=5,
                reserved_tokens=150,
                usage_complete=False,
            ),
        }
    )
    next_saved = save(store, fence, new, pending, next_event)
    unknown = next_event.model_copy(
        update={"kind": "model_unknown", "error_code": "MODEL_USAGE_UNKNOWN"}
    )
    after = save(
        store,
        fence,
        next_saved,
        pending.model_copy(update={"summary_revision": pending.summary_revision + 1}),
        unknown,
    )
    assert after.summary.usage.reserved_tokens == 150 and not after.summary.usage.usage_complete


@pytest.mark.parametrize(
    "changes",
    [
        {"call_id": str(uuid4())},
        {"input_reserved": 99},
        {"reservation_sha256": "e" * 64},
        {"role": "verification"},
        {"known_input_tokens": 101},
    ],
)
def test_bad_settlement_cannot_release_reserve(context, changes):
    store, fence, _ = context
    old, event = started(context)
    event = event.model_copy(
        update={
            "kind": "model_settled",
            "known_input_tokens": 10,
            "known_output_tokens": 5,
            **changes,
        }
    )
    summary = old.summary.model_copy(
        update={
            "summary_revision": old.summary.summary_revision + 1,
            "usage": Usage(model_calls=1, known_input_tokens=10, known_output_tokens=5),
        }
    )
    with pytest.raises(StoreError):
        save(store, fence, old, summary, event)
    assert store.get(summary.task_id).summary.usage.reserved_tokens == 150


def test_constructed_summary_and_event_free_text_rejected(context):
    store, fence, old = context
    bad = advanced(old, "checking").model_copy(update={"summary_revision": True})
    with pytest.raises(StoreError):
        save(store, fence, old, bad, AnalysisEvent(kind="phase_changed"))
    with pytest.raises(ValueError):
        AnalysisEvent(kind="finished", error_code="SECRET_VALUE")
    with pytest.raises(ValueError):
        AnalysisEvent.model_validate({"kind": "finished", "replacement": "SECRET_VALUE"})


def test_reconcile_requires_no_live_owner_and_preserves_unknown_usage(context):
    store, fence, _ = context
    old, _ = started(context)
    with pytest.raises(StoreError, match="^analysis_busy$"):
        store.reconcile(old.summary.task_id, old.summary.summary_revision, old.sha256)
    fence.close()
    saved = store.reconcile(old.summary.task_id, old.summary.summary_revision, old.sha256)
    assert saved.summary.state.outcome == "outcome_unknown"
    assert saved.summary.usage == old.summary.usage
    with AnalysisFence(store.directory, old.summary.task_id) as new_fence:
        with pytest.raises(StoreError, match="^analysis_terminal$"):
            save(
                store,
                new_fence,
                saved,
                saved.summary.model_copy(
                    update={"summary_revision": saved.summary.summary_revision + 1}
                ),
                AnalysisEvent(kind="finished"),
            )
    assert store.reconcile(
        saved.summary.task_id, saved.summary.summary_revision, saved.sha256
    ).reused


def reservation(context):
    store, fence, _ = context
    old = checking(context)
    request_id = str(uuid4())
    summary = old.summary.model_copy(
        update={"summary_revision": old.summary.summary_revision + 1, "usage": Usage(tool_calls=1)}
    )
    event = AnalysisEvent(
        kind="tool_started",
        role="diagnosis",
        tool="request_reproduction",
        call_id=request_id,
        request_sha256="e" * 64,
    )
    kwargs = dict(
        task_id=summary.task_id,
        request_id=request_id,
        payload_sha256="e" * 64,
        config=SandboxConfig(),
        case_sha256="f" * 64,
        summary=summary,
        expected_revision=old.summary.summary_revision,
        expected_sha256=old.sha256,
        fence=fence,
        event=event,
    )
    return kwargs


def test_execution_reservation_atomic_replay_binding_and_prune(context):
    store, _, _ = context
    kwargs = reservation(context)
    created = store.reserve_execution(**kwargs)
    assert created.created and created.claim and created.run.status == "running"
    assert created.summary.execution_record_ids == (created.run.run_id,)
    repeated = store.reserve_execution(**kwargs)
    assert not repeated.created and repeated.claim is None and repeated.run == created.run
    assert repeated.summary_sha256 == created.summary_sha256
    with pytest.raises(StoreError, match="^execution_link_conflict$"):
        store.reserve_execution(
            **(
                kwargs
                | {
                    "payload_sha256": "0" * 64,
                    "event": kwargs["event"].model_copy(update={"request_sha256": "0" * 64}),
                }
            )
        )
    with pytest.raises(StoreError, match="^execution_link_conflict$"):
        store.read_report(created.summary.task_id, str(uuid4()))
    with pytest.raises(StoreError, match="^report_not_found$"):
        store.read_report(created.summary.task_id, created.run.run_id)
    from tests.test_run_store import finish

    base = RunStore(store.directory)
    finish(base, created.claim)
    base.clock = lambda: datetime.now(UTC).timestamp() + 31 * 86400
    assert base.prune(apply=True) == []
    report = store.read_report(created.summary.task_id, created.run.run_id)
    assert report.record_id == created.run.run_id
    with pytest.raises(StoreError, match="^analysis_not_found$"):
        store.get_execution(str(uuid4()), kwargs["request_id"])
    base.close()


def test_reservation_transaction_rolls_back_on_claim_failure(context, monkeypatch):
    store, _, _ = context
    kwargs = reservation(context)
    before = store.get(kwargs["task_id"])

    def fail(*args, **kw):
        raise StoreError("store_unavailable")

    monkeypatch.setattr(store, "_claim", fail)
    with pytest.raises(StoreError):
        store.reserve_execution(**kwargs)
    assert store.get(kwargs["task_id"]).sha256 == before.sha256
    base = RunStore(store.directory)
    assert base.list_runs() == []
    assert store.get_execution(kwargs["task_id"], kwargs["request_id"]) is None
    base.close()


@pytest.mark.parametrize("target", ["summary", "event", "link"])
def test_corrupt_data_never_returned(context, target):
    store, _, old = context
    with store._transaction(write=True) as c:
        if target == "summary":
            c.execute(update(analysis_summaries).values(summary_json=b"SECRET_VALUE"))
        elif target == "event":
            c.execute(update(analysis_events).values(event_json=b"SECRET_VALUE"))
        else:
            c.exec_driver_sql("DELETE FROM analysis_events")
    with pytest.raises(StoreError, match="^analysis_corrupt$"):
        store.get(old.summary.task_id)


def test_api_read_only_empty_limits_and_corruption(context, monkeypatch, tmp_path):
    store, _, old = context
    monkeypatch.setenv("AWB_STATE_DIR", str(store.directory))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        listed = client.get("/api/analyses").json()["analyses"]
        assert len(listed) == 1 and listed[0]["sha256"] == old.sha256
        detail = client.get("/api/analyses/" + old.summary.task_id)
        assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store"
        assert detail.json()["events"][0]["event"]["kind"] == "created"
        assert client.post("/api/analyses").status_code == 405
        for suffix in ("?limit=0", "?limit=51", "?limit=-1", "?limit=1&limit=2"):
            assert client.get("/api/analyses" + suffix).status_code == 400
        assert client.get("/api/analyses/no-uuid").status_code == 400
        assert (
            client.get("/api/analyses", headers={"origin": "https://evil.test"}).status_code == 403
        )
        with store._transaction(write=True) as c:
            c.execute(update(analysis_summaries).values(summary_json=b"SECRET_VALUE"))
        response = client.get("/api/analyses")
        assert response.status_code == 503 and "SECRET" not in response.text
    monkeypatch.setenv("AWB_STATE_DIR", str(tmp_path / "missing"))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.get("/api/analyses").json() == {"analyses": []}
        assert client.get("/api/analyses/" + str(uuid4())).status_code == 404
    assert not (tmp_path / "missing").exists()


def test_v0002_upgrade_backup_restore_preserves_existing_web_data(tmp_path):
    directory = tmp_path / "state"
    directory.mkdir()
    base = RunStore(directory)
    sqlite3.connect(base.path).close()
    with base._database().connect() as c:
        c.exec_driver_sql("BEGIN IMMEDIATE")
        command.upgrade(base._migration(c), "0002_web_requests")
        c.exec_driver_sql("INSERT INTO web_requests VALUES (?, ?, 0, 0)", (str(uuid4()), "a" * 64))
        c.commit()
    with sqlite3.connect(base.path) as old, sqlite3.connect(tmp_path / "backup") as backup:
        old.backup(backup)
        before = old.execute("SELECT * FROM web_requests").fetchall()
    with pytest.raises(StoreError, match="^schema_incompatible$"):
        base.list_runs()
    base.initialize()
    with base._transaction() as c:
        assert [tuple(r) for r in c.exec_driver_sql("SELECT * FROM web_requests")] == before
    with pytest.raises(StoreError, match="^migration_not_empty$"):
        base.downgrade_empty()
    base.close()
    with sqlite3.connect(tmp_path / "backup") as backup, sqlite3.connect(base.path) as restored:
        backup.backup(restored)
        assert restored.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0002_web_requests",
        )
        assert restored.execute("SELECT * FROM web_requests").fetchall() == before


def test_event_insert_failure_rolls_back_summary_and_no_send_permission(context):
    store, fence, old = context
    with store._transaction(write=True) as c:
        c.exec_driver_sql(
            "CREATE TRIGGER reject_analysis_event BEFORE INSERT ON analysis_events "
            "BEGIN SELECT RAISE(ABORT, 'synthetic'); END"
        )
    with pytest.raises(StoreError):
        save(store, fence, old, advanced(old, "checking"), AnalysisEvent(kind="phase_changed"))
    assert store.get(old.summary.task_id).sha256 == old.sha256
    assert len(store.events(old.summary.task_id)) == 1


def test_event_and_summary_size_caps_and_wrong_fence(context):
    store, fence, old = context
    with pytest.raises(StoreError, match="^owner_lock_required$"):
        with AnalysisFence(store.directory, str(uuid4())) as other:
            save(store, other, old, advanced(old, "checking"), AnalysisEvent(kind="phase_changed"))
    for revision in (True, 1.0, -1, 256):
        with pytest.raises(StoreError, match="^invalid_revision$"):
            store.save(
                advanced(old, "checking"),
                AnalysisEvent(kind="phase_changed"),
                expected_revision=revision,
                expected_sha256=old.sha256,
                fence=fence,
            )
    assert store.get(old.summary.task_id).sha256 == old.sha256


def test_unknown_reservation_prevents_further_model_send(context):
    store, fence, _ = context
    old, event = started(context)
    unknown = save(
        store,
        fence,
        old,
        old.summary.model_copy(update={"summary_revision": old.summary.summary_revision + 1}),
        event.model_copy(update={"kind": "model_unknown", "error_code": "MODEL_USAGE_UNKNOWN"}),
    )
    with pytest.raises(StoreError, match="^analysis_unsettled_call$"):
        save(
            store,
            fence,
            unknown,
            unknown.summary.model_copy(
                update={
                    "summary_revision": unknown.summary.summary_revision + 1,
                    "usage": Usage(model_calls=2, reserved_tokens=300, usage_complete=False),
                }
            ),
            event.model_copy(update={"call_id": str(uuid4())}),
        )


def test_current_summary_must_match_persisted_accounting_ledger(context):
    store, _, _ = context
    old, _ = started(context)
    forged = old.summary.model_copy(
        update={"usage": Usage(model_calls=1, reserved_tokens=149, usage_complete=False)}
    )
    raw = canonical(forged.model_dump(mode="json"))
    with store._transaction(write=True) as c:
        c.execute(update(analysis_summaries).values(summary_json=raw, sha256=digest(raw)))
    with pytest.raises(StoreError, match="^analysis_corrupt$"):
        store.get(old.summary.task_id)


def child_fence(directory, task_id, queue):
    from pathlib import Path

    try:
        with AnalysisFence(Path(directory), task_id):
            queue.put("acquired")
    except StoreError as error:
        queue.put(error.code)


def test_another_process_cannot_recover_live_owner(context, monkeypatch):
    import multiprocessing
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    store, fence, old = context
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    process = ctx.Process(
        target=child_fence, args=(str(store.directory), old.summary.task_id, queue)
    )
    process.start()
    process.join(10)
    try:
        assert process.exitcode == 0
        assert queue.get(timeout=1) == "analysis_busy"
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
    fence.close()
    process = ctx.Process(
        target=child_fence, args=(str(store.directory), old.summary.task_id, queue)
    )
    process.start()
    process.join(10)
    assert process.exitcode == 0 and queue.get(timeout=1) == "acquired"


def test_task_cannot_bind_an_existing_foreign_record(context):
    store, fence, old = context
    base = RunStore(store.directory)
    foreign = base.create("isolated-fixture", "pass", "0" * 64, "1" * 64)
    with pytest.raises(StoreError, match="^execution_link_conflict$"):
        save(
            store,
            fence,
            old,
            advanced(old, "checking", execution_record_ids=(foreign.run_id,)),
            AnalysisEvent(kind="phase_changed"),
        )
    assert base.detail(foreign.run_id).run.status == "queued"
    base.close()


def test_suppressed_cas_update_does_not_append_event_or_grant_permission(context):
    store, fence, old = context
    with store._transaction(write=True) as c:
        c.exec_driver_sql(
            "CREATE TRIGGER suppress_update BEFORE UPDATE ON analysis_summaries "
            "BEGIN SELECT RAISE(IGNORE); END"
        )
    with pytest.raises(StoreError, match="^analysis_conflict$"):
        save(store, fence, old, advanced(old, "checking"), AnalysisEvent(kind="phase_changed"))
    assert store.get(old.summary.task_id).sha256 == old.sha256
    assert len(store.events(old.summary.task_id)) == 1


@pytest.mark.anyio
async def test_short_run_reconcile_skips_paused_analysis_owner(context, monkeypatch):
    import multiprocessing
    import os
    import signal
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    from agent_workbench.run_store import execution
    from tests.test_reviewer_analysis_store import hold_owner

    store, fence, _ = context
    reserved = store.reserve_execution(**reservation(context))
    fence.close()
    spawn = multiprocessing.get_context("spawn")
    ready = spawn.Event()
    owner = spawn.Process(
        target=hold_owner, args=(str(store.directory), reserved.summary.task_id, ready)
    )
    base = RunStore(store.directory, clock=lambda: datetime.now(UTC).timestamp() + 121)
    observed = []

    class ReadOnlyDocker:
        async def inspect(self, name):
            observed.append(name)
            return None

    async def connect():
        return ReadOnlyDocker()

    monkeypatch.setattr(execution.DockerControl, "connect", connect)
    owner.start()
    try:
        assert ready.wait(10)
        os.kill(owner.pid, signal.SIGSTOP)
        assert len(base.expired()) == 1
        assert await execution.reconcile_runs(base) == []
        assert observed == []
        assert base.detail(reserved.run.run_id).run.status == "running"
        owner.kill()
        owner.join(5)
        assert owner.exitcode == -signal.SIGKILL
        recovered = await execution.reconcile_runs(base)
        assert len(recovered) == 1
        assert recovered[0].status == "outcome_unknown"
        assert recovered[0].executor_state == "absent"
        assert observed == ["awb-p003-" + reserved.run.attempt_id]
        replay = store.get_execution(reserved.summary.task_id, reserved.run.run_id)
        assert replay is None  # lookup is by request ID, never execution ID
        assert store.get(reserved.summary.task_id).summary == reserved.summary
    finally:
        if owner.is_alive():
            owner.kill()
            owner.join(5)
        base.close()
