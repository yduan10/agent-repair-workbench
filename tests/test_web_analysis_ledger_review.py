"""Independent P1-01b B1 counterexamples; real temporary SQLite, no model network."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import event

from agent_workbench.analysis_store.models import AnalysisEvent
from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import Report
from agent_workbench.orchestration.policy import transition
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.models import ExecutionEvidence, SandboxReport
from tests.test_web_analysis_store import admit, host, reserve_link, sql

__all__ = ["host"]


def test_two_concurrent_claim_consumers_only_advance_once(host):
    store, request, _, adapter, _, fence = host
    admission = admit(host)
    barrier = Barrier(2)

    def start():
        barrier.wait(timeout=5)
        try:
            return store.start_created(
                admission.claim, admission.saved, fence=fence, case_name=request.case_name
            ).saved.summary.summary_revision
        except StoreError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: start(), range(2)))
    assert sorted(results, key=str) == [1, "admission_invalid"]
    assert adapter.calls == 0
    assert sql(store, "SELECT consumed FROM web_analysis_requests") == [(1,)]
    assert [v.event.kind for v in store.events(request.request_id)] == ["created", "phase_changed"]


@pytest.mark.parametrize(
    "error_code", ["cleanup_unconfirmed", "create_unconfirmed", "attach_cleanup_unconfirmed"]
)
def test_cleanup_label_alone_cannot_release_slot_with_uncertain_error(host, error_code):
    store, request, _, _, owner, fence = host
    admission = admit(host)
    started = store.start_created(
        admission.claim, admission.saved, fence=fence, case_name=request.case_name
    ).saved
    execution = reserve_link(store, started, fence)
    old = execution.summary
    terminal = old.model_copy(
        update={
            "state": transition(
                old.state,
                "finished",
                expected_revision=old.state.revision,
                outcome="outcome_unknown",
            ),
            "summary_revision": old.summary_revision + 1,
            "finished_at": datetime.now(UTC),
        }
    )
    store.save(
        terminal,
        AnalysisEvent(kind="finished", error_code="INTERRUPTED"),
        expected_revision=old.summary_revision,
        expected_sha256=execution.summary_sha256,
        fence=fence,
    )
    claim = execution.claim
    report = SandboxReport(
        run_id=claim.run.attempt_id,
        record_id=claim.run.run_id,
        mcp=MCPReport(
            invocation_id="independent",
            adapter_outcome="completed",
            contract_report=Report(status="passed"),
        ),
        execution=ExecutionEvidence(cleanup="removed", error=error_code),
    )
    args = (
        claim.run.run_id,
        claim.run.attempt_id,
        claim.token,
        claim.run.version,
        "outcome_unknown",
        report,
        "absent",
    )
    if error_code == "create_unconfirmed":
        # Existing RunStore rejects this contradictory combination even before slot release.
        with pytest.raises(StoreError, match="^invalid_status$"):
            store._base.finish(*args)
    else:
        store._base.finish(*args)
    assert store.release_safe(owner) is False
    assert store.active_id() == request.request_id


def test_failed_0007_index_creation_rolls_back_table_and_revision(tmp_path):
    store = RunStore(tmp_path / "review-migration")
    store.initialize()
    try:
        run = store.create("isolated-fixture", "pass", "a" * 64, "b" * 64)
        with store._transaction(write=True) as connection:
            command.downgrade(store._migration(connection), "0006_reproductions")
        engine = store._database()

        def fail(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("CREATE UNIQUE INDEX ux_web_analysis_active"):
                raise RuntimeError("independent migration interruption")

        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(RuntimeError, match="independent migration interruption"):
                store.initialize()
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").all() == [
                ("0006_reproductions",)
            ]
            assert (
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE name='web_analysis_requests'"
                ).all()
                == []
            )
        store.initialize()
        assert store.detail(run.run_id).run == run
    finally:
        store.close()


def test_cancel_does_not_consume_or_destroy_original_claim(host):
    store, request, runtime, adapter, owner, fence = host
    admission = admit(host)
    assert store.request_cancel(request.request_id)
    replay = store.existing(request)
    assert replay.cancel_requested is True and replay.claim is None
    assert sql(store, "SELECT consumed,active FROM web_analysis_requests") == [(0, 1)]
    assert store.release_safe(owner) is False
    started = store.start_created(
        admission.claim, admission.saved, fence=fence, case_name=request.case_name
    )
    assert started.cancel_requested and adapter.calls == 0
    assert sql(store, "SELECT consumed,active FROM web_analysis_requests") == [(1, 1)]
