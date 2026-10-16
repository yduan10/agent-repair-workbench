"""Independent B2 resource-boundary counterexamples; isolated SQLite/fake Docker."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_workbench.analysis_store.models import AnalysisEvent
from agent_workbench.candidate_execution import oracle
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.orchestration.policy import transition
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner import service
from agent_workbench.runner.docker import DockerFailure
from agent_workbench.web_repairs.recovery import terminated
from agent_workbench.web_runs.fencing import OwnerFence
from tests.test_sandbox_lifecycle import CASE, anyio_backend, fake
from tests.test_web_admission import request, store
from tests.test_web_analysis_store import admit, host, reserve_link

__all__ = ["anyio_backend", "fake", "host", "store"]


@pytest.mark.parametrize("observed", ["absent", "stopped"])
def test_reconciled_observation_never_releases_reproduction_slot(store, observed):
    with OwnerFence(store.directory) as owner:
        claim = store.admit(request(), owner)
        recovery = RunStore(store.directory, clock=lambda: datetime.now(UTC).timestamp() + 121)
        try:
            recovery.reconcile(claim.run.run_id, claim.run.version, executor_state=observed)
        finally:
            recovery.close()
        assert not store.release_safe(owner)
        assert store.active_id() == claim.run.run_id


@pytest.mark.parametrize("observed", ["absent", "stopped"])
def test_reconciled_observation_never_releases_analysis_slot(host, observed):
    store, request, _, _, owner, fence = host
    admission = admit(host)
    started = store.start_created(
        admission.claim, admission.saved, fence=fence, case_name=request.case_name
    ).saved
    execution = reserve_link(store, started, fence)
    old = execution.summary
    # Reservation links the run before any external invocation can start.
    assert old.execution_record_ids == (execution.run.run_id,)
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
    recovery = RunStore(store.directory, clock=lambda: datetime.now(UTC).timestamp() + 121)
    try:
        recovery.reconcile(execution.run.run_id, execution.run.version, executor_state=observed)
    finally:
        recovery.close()
    assert not store.release_safe(owner)
    assert store.active_id() == request.request_id


@pytest.mark.anyio
async def test_attach_cleanup_failure_is_not_hidden_by_prior_execution_error(fake, monkeypatch):
    async def fail_session(*args):
        raise DockerFailure("container_failed")

    async def fail_close(*args):
        raise TimeoutError

    monkeypatch.setattr(service._Run, "session", fail_session)
    monkeypatch.setattr(service, "_close_attach", fail_close)
    report = await service.run_sandbox(b"{}", CASE)
    assert report.execution.cleanup == "removed"
    assert report.execution.error == "attach_cleanup_unconfirmed"


@pytest.mark.anyio
@pytest.mark.parametrize("late_error", ["wire", "snapshot", "image", "oracle", "cleanup", "cancel"])
async def test_oracle_postflight_error_cannot_hide_unclosed_attach(
    fake, monkeypatch, tmp_path, late_error
):
    snapshot = SnapshotStore(tmp_path / "snapshots").create_baseline(str(uuid4()))
    entered = asyncio.Event()

    class Candidate:
        started = True

        def __init__(self, *args):
            pass

        async def create(self):
            return "a" * 64

        async def verify(self):
            pass

        async def cleanup(self):
            return late_error != "cleanup"

    @asynccontextmanager
    async def transport(process, state):
        if late_error == "wire":
            state.error = "frame_too_large"
        yield None, None

    async def fail_sequence(*args):
        entered.set()
        if late_error == "cancel":
            await asyncio.Event().wait()
        raise DockerFailure("container_failed")

    async def fail_close(*args):
        raise TimeoutError

    original_verify = SnapshotStore.verify
    snapshot_calls = image_calls = oracle_calls = 0

    def verify_snapshot(self, handle):
        nonlocal snapshot_calls
        snapshot_calls += 1
        if late_error == "snapshot" and snapshot_calls > 1:
            raise OSError
        return original_verify(self, handle)

    def verify_image(root):
        nonlocal image_calls
        image_calls += 1
        if late_error == "image" and image_calls > 1:
            raise ValueError
        return service.verified_image()

    def verify_oracle():
        nonlocal oracle_calls
        oracle_calls += 1
        return not (late_error == "oracle" and oracle_calls > 1)

    monkeypatch.setattr(oracle, "DockerControl", fake)
    monkeypatch.setattr(oracle, "CandidateDockerControl", Candidate)
    monkeypatch.setattr(SnapshotStore, "verify", verify_snapshot)
    monkeypatch.setattr(oracle, "verified_image", verify_image)
    monkeypatch.setattr(oracle, "verify_oracle", verify_oracle)
    monkeypatch.setattr(oracle, "bounded_transport", transport)
    monkeypatch.setattr(oracle, "EvidenceSession", service.EvidenceSession)
    monkeypatch.setattr(oracle.SequenceOracle, "run", fail_sequence)
    monkeypatch.setattr(oracle, "_close_attach", fail_close)
    running = asyncio.create_task(
        oracle.run_oracle(snapshot, scenario="pass", attempt_id=str(uuid4()), image_root=tmp_path)
    )
    if late_error == "cancel":
        await entered.wait()
        running.cancel()
    report = await running
    assert report.cleanup == ("unconfirmed" if late_error == "cleanup" else "removed")
    assert not terminated(report)
    assert report.error == "attach_cleanup_unconfirmed"
    assert report.status == "outcome_unknown"
