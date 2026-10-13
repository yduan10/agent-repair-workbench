from __future__ import annotations

import multiprocessing
import sqlite3
import threading
from pathlib import Path
from queue import Empty
from time import monotonic

import pytest

from agent_workbench.run_store import RunStore, StoreError
from tests.test_run_store import claimed, finish, queued


def claim_worker(directory, run_id, barrier, queue):
    store = RunStore(Path(directory))
    barrier.wait(timeout=10)
    try:
        claim = store.claim(run_id, 1)
        queue.put(("claimed", claim.run.attempt_id))
    except StoreError as error:
        queue.put((error.code, None))
    finally:
        store.close()


def init_worker(directory, barrier, queue):
    store = RunStore(Path(directory))
    barrier.wait(timeout=10)
    try:
        store.initialize()
        queue.put("initialized")
    except StoreError as error:
        queue.put(error.code)
    finally:
        store.close()


def join_results(workers, queue):
    for worker in workers:
        worker.start()
    try:
        results = [queue.get(timeout=15) for _ in workers]
        for worker in workers:
            worker.join(timeout=5)
            assert worker.exitcode == 0
        return results
    except Empty:
        pytest.fail("worker failed to return a bounded result")
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.kill()
                worker.join(timeout=5)


def test_real_processes_only_one_claim(tmp_path: Path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    store = RunStore(tmp_path / "db")
    store.initialize()
    run = queued(store)
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(2), context.Queue()
    workers = [
        context.Process(
            target=claim_worker, args=(str(store.directory), run.run_id, barrier, queue)
        )
        for _ in range(2)
    ]
    results = join_results(workers, queue)
    assert sorted(result[0] for result in results) == ["claimed", "version_conflict"]
    assert [e.kind for e in store.detail(run.run_id).events] == ["created", "claimed"]


def test_real_processes_concurrent_initialize(tmp_path: Path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    context = multiprocessing.get_context("spawn")
    barrier, queue = context.Barrier(3), context.Queue()
    directory = tmp_path / "db"
    workers = [
        context.Process(target=init_worker, args=(str(directory), barrier, queue)) for _ in range(3)
    ]
    results = join_results(workers, queue)
    assert all(result in ("initialized", "store_busy") for result in results)
    assert "initialized" in results
    store = RunStore(directory)
    store.initialize()
    assert store.list_runs() == []
    assert queued(store).version == 1


def test_real_sqlite_busy_is_bounded_and_no_write(tmp_path: Path):
    store = RunStore(tmp_path / "db")
    store.initialize()
    run = queued(store)
    with sqlite3.connect(store.path) as holder:
        holder.execute("BEGIN IMMEDIATE")
        start = monotonic()
        with pytest.raises(StoreError, match="^store_busy$"):
            store.claim(run.run_id, 1)
        assert 0.7 <= monotonic() - start < 3
        holder.rollback()
    assert store.detail(run.run_id).run == run
    assert len(store.detail(run.run_id).events) == 1


def test_read_snapshot_survives_concurrent_prune(tmp_path: Path, monkeypatch):
    now = [1000.0]
    writer = RunStore(tmp_path / "db", clock=lambda: now[0])
    writer.initialize()
    run = finish(writer, claimed(writer))
    now[0] += 31 * 86400
    ready = threading.Barrier(3)
    proceed = threading.Event()
    original = RunStore._report
    outputs, errors = [], []

    def blocked_report(connection, view):
        # report() has read run metadata in a genuine SQLite BEGIN snapshot already.
        if threading.current_thread().name.startswith("reader"):
            ready.wait(timeout=5)
            assert proceed.wait(timeout=5)
        return original(connection, view)

    monkeypatch.setattr(RunStore, "_report", staticmethod(blocked_report))

    def read():
        reader = RunStore(writer.directory)
        try:
            outputs.append(reader.report(run.run_id))
        except Exception as error:
            errors.append(error)
        finally:
            reader.close()

    threads = [threading.Thread(target=read, name=f"reader-{i}") for i in range(2)]
    for thread in threads:
        thread.start()
    try:
        ready.wait(timeout=5)
        assert writer.prune(apply=True) == [run.run_id]
    finally:
        proceed.set()
        for thread in threads:
            thread.join(timeout=5)
            assert not thread.is_alive()
    assert errors == []
    assert len(outputs) == 2
    assert all(report.record_id == run.run_id for report in outputs)
    with pytest.raises(StoreError, match="^not_found$"):
        writer.report(run.run_id)
