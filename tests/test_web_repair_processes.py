"""B1-03/04/07: actual OS processes and flock, with bounded IPC and cleanup."""

import multiprocessing as mp
import os
import signal
from pathlib import Path

import pytest

from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairTask
from agent_workbench.run_store.models import StoreError
from agent_workbench.web_repairs.fencing import RepairWebFence
from agent_workbench.web_repairs.models import RepairRequest
from agent_workbench.web_repairs.store import WebRepairStore
from tests.test_web_repair_store import POLICY, admit, consume, host, task_for, uid

__all__ = ["host"]


@pytest.fixture(autouse=True)
def spawn_import_path(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))


def contender(directory, request_json, task_json, barrier, release, pipe):
    store = WebRepairStore(directory)
    request = RepairRequest.model_validate_json(request_json)
    task = RepairTask.model_validate_json(task_json)
    try:
        barrier.wait(timeout=10)
        with (
            RepairWebFence(directory) as owner,
            RepairFence(directory, request.request_id) as fence,
        ):
            result = store.admit(request, task, policy_sha256=POLICY, owner=owner, task_fence=fence)
            pipe.send("claim" if result.claim else "reused")
            assert release.wait(timeout=10)
    except StoreError as error:
        pipe.send(error.code)
    finally:
        pipe.close()
        store.close()


def kill(process):
    if process.is_alive():
        process.kill()
    process.join(timeout=5)
    assert not process.is_alive()


@pytest.mark.parametrize("same_id", [True, False])
def test_two_processes_admit_one_active_claim(tmp_path, same_id):
    ctx = mp.get_context("spawn")
    directory = tmp_path / "state"
    store = WebRepairStore(directory)
    store.initialize()
    first = RepairRequest(request_id=uid(), case_id="output_mismatch", mode="single_role")
    requests = [first, first if same_id else first.model_copy(update={"request_id": uid()})]
    barrier, release = ctx.Barrier(2), ctx.Event()
    processes, pipes = [], []
    try:
        for request in requests:
            parent, child = ctx.Pipe()
            process = ctx.Process(
                target=contender,
                args=(
                    directory,
                    request.model_dump_json(),
                    task_for(tmp_path, request, 1_700_000_000).model_dump_json(),
                    barrier,
                    release,
                    child,
                ),
            )
            process.start()
            child.close()
            processes.append(process)
            pipes.append(parent)
        results = []
        for pipe in pipes:
            assert pipe.poll(15)
            results.append(pipe.recv())
        assert sorted(results) == ["claim", "repair_busy"]
        release.set()
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        with store._base._transaction() as connection:
            assert connection.exec_driver_sql(
                "SELECT active,consumed FROM web_repair_requests"
            ).all() == [(1, 0)]
    finally:
        release.set()
        for process in processes:
            kill(process)
        for pipe in pipes:
            pipe.close()
        store.close()


def test_inherited_claim_cannot_execute_after_fork(host):
    admission = admit(host)
    parent, child = mp.get_context("fork").Pipe()

    def inherited():
        try:
            consume(host, admission)
            child.send("unexpected")
        except StoreError as error:
            child.send(error.code)
        finally:
            child.close()

    process = mp.get_context("fork").Process(target=inherited)
    try:
        process.start()
        child.close()
        assert parent.poll(10)
        assert parent.recv() == "owner_lock_required"
        process.join(timeout=5)
        assert process.exitcode == 0
        assert not host[0].receipt(host[1].request_id).consumed
        assert consume(host, admission).executable
    finally:
        kill(process)
        parent.close()


def test_sigstop_lock_and_sigkill_receipt_no_replay(tmp_path):
    ctx = mp.get_context("spawn")
    directory = tmp_path / "state"
    store = WebRepairStore(directory)
    store.initialize()
    request = RepairRequest(request_id=uid(), case_id="counter_offset", mode="three_role")
    task = task_for(tmp_path, request, 1_700_000_000)
    parent, child = ctx.Pipe()
    barrier, release = ctx.Barrier(1), ctx.Event()
    process = ctx.Process(
        target=contender,
        args=(
            directory,
            request.model_dump_json(),
            task.model_dump_json(),
            barrier,
            release,
            child,
        ),
    )
    try:
        process.start()
        child.close()
        assert parent.poll(15) and parent.recv() == "claim"
        os.kill(process.pid, signal.SIGSTOP)
        _, status = os.waitpid(process.pid, os.WUNTRACED)
        assert os.WIFSTOPPED(status)
        with pytest.raises(StoreError, match="repair_busy"):
            with RepairWebFence(directory):
                pass
        kill(process)
        with (
            RepairWebFence(directory) as owner,
            RepairFence(directory, request.request_id) as fence,
        ):
            replay = store.admit(request, task, policy_sha256=POLICY, owner=owner, task_fence=fence)
            assert replay.claim is None
            assert store.receipt(request.request_id).active
            assert not store.receipt(request.request_id).consumed
            other = request.model_copy(update={"request_id": uid()})
            with RepairFence(directory, other.request_id) as other_fence:
                with pytest.raises(StoreError, match="recovery_required"):
                    store.admit(
                        other,
                        task_for(tmp_path, other, 1_700_000_000),
                        policy_sha256=POLICY,
                        owner=owner,
                        task_fence=other_fence,
                    )
    finally:
        kill(process)
        parent.close()
        store.close()
