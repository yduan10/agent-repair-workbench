"""Independent B1a contract counterexamples; local temporary SQLite only."""

import sqlite3
from dataclasses import asdict

import pytest
from fastapi.encoders import jsonable_encoder

from agent_workbench.run_store.models import StoreError
from tests.test_web_repair_store import admit, consume, host, sql

__all__ = ["host"]


def test_private_claim_rejects_framework_serialization(host):
    admission = admit(host)
    for private in (admission.claim, admission):
        with pytest.raises((TypeError, ValueError)):
            jsonable_encoder(private)
    with pytest.raises((TypeError, ValueError)):
        asdict(admission.claim)


def test_consumed_receipt_cannot_be_rewound_and_replay_claim(host):
    admission = admit(host)
    assert consume(host, admission).executable
    store, request, *_ = host
    try:
        sql(store, "UPDATE web_repair_requests SET consumed=0")
    except sqlite3.IntegrityError:
        pass  # A database monotonicity constraint is also acceptable.
    with pytest.raises(StoreError):
        consume(host, admission)
    assert store.receipt(request.request_id).consumed


def test_owner_reacquired_while_consume_waits_for_transaction_is_rejected(host):
    from sqlalchemy import event

    admission = admit(host)
    store, request, _, owner, _, _ = host
    engine = store._base._database()
    changed = False

    def change_owner(conn, cursor, statement, parameters, context, many):
        nonlocal changed
        if statement == "BEGIN IMMEDIATE" and not changed:
            changed = True
            owner.close()
            owner.acquire()

    event.listen(engine, "before_cursor_execute", change_owner)
    try:
        with pytest.raises(StoreError, match="owner_lock_required"):
            consume(host, admission)
    finally:
        event.remove(engine, "before_cursor_execute", change_owner)
    assert not store.receipt(request.request_id).consumed


def test_persisted_cancel_and_receipt_tombstone_cannot_be_removed(host):
    admission = admit(host)
    store, request, *_ = host
    store.request_cancel(request.request_id)
    for statement in (
        "UPDATE web_repair_requests SET cancel_requested=0",
        "DELETE FROM web_repair_requests",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            sql(store, statement)
    assert not consume(host, admission).executable
    assert store.receipt(request.request_id).cancel_requested


@pytest.mark.parametrize(
    "guard", ["web_repair_immutable", "web_repair_monotonic", "web_repair_tombstone"]
)
def test_missing_database_guard_refuses_read_and_consume(host, guard):
    admission = admit(host)
    store, request, *_ = host
    sql(store, f"DROP TRIGGER {guard}")
    with pytest.raises(StoreError, match="schema_incompatible"):
        store.receipt(request.request_id)
    with pytest.raises(StoreError, match="schema_incompatible"):
        consume(host, admission)


def test_replaced_lock_inode_refuses_claim(host):
    admission = admit(host)
    store, _, _, owner, _, _ = host
    path = owner.directory / "repair-web-owner.lock"
    path.unlink()
    path.touch(mode=0o600)
    with pytest.raises(StoreError, match="owner_lock_required"):
        consume(host, admission)
    assert not store.receipt(host[1].request_id).consumed


@pytest.mark.parametrize("fence_index", [3, 4])
def test_close_waits_for_consume_commit_guard(host, fence_index):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from sqlalchemy import event

    admission = admit(host)
    store = host[0]
    engine = store._base._database()
    in_transaction, release, closing, closed = (Event() for _ in range(4))

    def wait_before_begin(conn, cursor, statement, parameters, context, many):
        if statement == "BEGIN IMMEDIATE":
            in_transaction.set()
            assert release.wait(5)

    def close_owner():
        closing.set()
        host[fence_index].close()
        closed.set()

    event.listen(engine, "before_cursor_execute", wait_before_begin)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            started = executor.submit(consume, host, admission)
            assert in_transaction.wait(5)
            stopped = executor.submit(close_owner)
            try:
                assert closing.wait(5)
                assert not closed.wait(0.05)
            finally:
                release.set()
            assert started.result(timeout=5).executable
            stopped.result(timeout=5)
            assert closed.is_set()
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", wait_before_begin)
    assert store.receipt(host[1].request_id).consumed
