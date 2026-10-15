"""Independent recovery fault probes: temporary state and bounded Docker double."""

import asyncio

import pytest

from agent_workbench.repair_recovery.service import RecoveryService
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.run_store.models import StoreError
from agent_workbench.runner.docker import DockerFailure
from tests.test_repair_comparisons import ctx as ctx
from tests.test_repair_recovery import run, setup
from tests.test_repair_reproductions import repro as repro


def test_remove_ack_lost_does_not_reconcile_and_next_apply_is_safe(repro, monkeypatch):
    r, store, fake, pending = setup(repro)
    original = fake.command

    async def lost_ack(*argv):
        result = await original(*argv)
        if argv[:3] == ("container", "rm", "--force"):
            raise DockerFailure("private transport exception")
        return result

    monkeypatch.setattr(fake, "command", lost_ack)
    result = run(store, fake, r[5], pending.task.task_id, True)
    assert result.error == "RESOURCE_UNVERIFIED" and result.requires_reconcile
    assert store.get(pending.task.task_id).task == pending.task
    assert "private" not in result.model_dump_json()
    assert len(fake.removed) == 1 and not fake.items
    result = run(store, fake, r[5], pending.task.task_id, True)
    assert result.exit_code() == 0 and result.outcome == "outcome_unknown"
    assert store.get(pending.task.task_id).task.usage == pending.task.usage
    assert len(fake.removed) == 1
    store.close()


def test_owner_fence_covers_all_docker_operations(repro, monkeypatch):
    r, store, fake, pending = setup(repro)
    command, inspect = fake.command, fake.inspect
    calls = []

    def assert_locked():
        with pytest.raises(StoreError, match="repair_busy"):
            with RepairFence(store.directory, pending.task.task_id):
                pass
        calls.append(1)

    async def guarded_command(*argv):
        assert_locked()
        return await command(*argv)

    async def guarded_inspect(cid):
        assert_locked()
        return await inspect(cid)

    monkeypatch.setattr(fake, "command", guarded_command)
    monkeypatch.setattr(fake, "inspect", guarded_inspect)
    result = run(store, fake, r[5], pending.task.task_id, True)
    assert result.exit_code() == 0 and len(calls) >= 6
    with RepairFence(store.directory, pending.task.task_id):
        pass
    store.close()


def test_replacement_after_removal_is_not_removed_or_claimed_absent(repro, monkeypatch):
    import copy

    r, store, fake, pending = setup(repro)
    original = fake.command
    replacement = copy.deepcopy(fake.items["a" * 64])
    replacement["Id"] = "b" * 64

    async def replace(*argv):
        result = await original(*argv)
        if argv[:3] == ("container", "rm", "--force"):
            fake.items["b" * 64] = replacement
        return result

    monkeypatch.setattr(fake, "command", replace)
    result = run(store, fake, r[5], pending.task.task_id, True)
    assert result.error == "RESOURCE_UNVERIFIED" and result.requires_reconcile
    assert fake.removed == ["a" * 64] and list(fake.items) == ["b" * 64]
    assert store.get(pending.task.task_id).task == pending.task
    store.close()


def test_cancellation_during_remove_keeps_ledger_unknown_and_releases_fence(repro, monkeypatch):
    r, store, fake, pending = setup(repro)
    original = fake.command

    async def exercise():
        entered = asyncio.Event()

        async def wait(*argv):
            if argv[:3] == ("container", "rm", "--force"):
                entered.set()
                await asyncio.Event().wait()
            return await original(*argv)

        monkeypatch.setattr(fake, "command", wait)
        task = asyncio.create_task(
            RecoveryService(store, r[5], fake).recover(pending.task.task_id, apply=True)
        )
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert not fake.removed and store.get(pending.task.task_id).task == pending.task
    with RepairFence(store.directory, pending.task.task_id):
        pass
    store.close()


@pytest.mark.parametrize("output", [b"a" * 64 + b"\n" + b"b" * 64, b"\xff"])
def test_ambiguous_scan_never_removes_or_reconciles(repro, monkeypatch, output):
    r, store, fake, pending = setup(repro)

    async def scan(*argv):
        assert argv[:2] == ("container", "ls")
        return output

    monkeypatch.setattr(fake, "command", scan)
    result = run(store, fake, r[5], pending.task.task_id, True)
    assert result.error == "RESOURCE_UNVERIFIED" and result.requires_reconcile
    assert not fake.removed and store.get(pending.task.task_id).task == pending.task
    store.close()
