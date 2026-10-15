"""Recovery safety: real SQLite and snapshots, explicit deterministic Docker double."""

import asyncio
import copy
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution.docker import ENTRYPOINT, PROJECT, SNAPSHOT_LABEL
from agent_workbench.candidates.snapshots import SnapshotHandle
from agent_workbench.repair_recovery.inventory import RecoveryInventory
from agent_workbench.repair_recovery.service import RecoveryService
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.runner.docker import PROJECT_LABEL, RUN_LABEL, DockerFailure
from tests.test_repair_comparisons import cas, reserve
from tests.test_repair_comparisons import ctx as ctx
from tests.test_repair_reproductions import repro as repro
from tests.test_repair_reproductions import reserve_t05


class FakeDocker:
    def __init__(self):
        self.items = {}
        self.removed = []
        self.fail_remove = False

    async def command(self, *argv):
        if argv[:2] == ("container", "ls"):
            name = argv[argv.index("--filter") + 1][7:-1]
            found = [cid for cid, i in self.items.items() if i["Name"] == "/" + name]
            return "\n".join(found).encode()
        assert argv[:3] == ("container", "rm", "--force")
        if self.fail_remove:
            raise DockerFailure("synthetic_failure")
        self.removed.append(argv[3])
        self.items.pop(argv[3], None)
        return b""

    async def inspect(self, cid):
        return copy.deepcopy(self.items.get(cid))


def relocate(repro):
    """Recovery only derives the documented state-owned snapshot root."""
    oldroot = repro[4].root.parent
    root = repro[0].directory / "repair-snapshots"
    oldroot.rename(root)
    baseline = SnapshotHandle(repro[4].ref, root / repro[4].ref.snapshot_id)
    candidate = SnapshotHandle(repro[-1][5].ref, root / repro[-1][5].ref.snapshot_id)
    ctx = (*repro[-1][:4], baseline, candidate, repro[-1][6])
    return (*repro[:4], baseline, repro[5], ctx)


def item(target, directory, cid="a" * 64):
    return {
        "Id": cid,
        "Name": "/awb-p006-" + target.attempt_id,
        "Image": target.image_id,
        "Config": {
            "Image": target.image_id,
            "Cmd": ["--scenario", target.scenario],
            "Entrypoint": ENTRYPOINT,
            "Labels": {
                PROJECT_LABEL: PROJECT,
                RUN_LABEL: target.attempt_id,
                SNAPSHOT_LABEL: target.snapshot.tree_sha256,
            },
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(directory / "repair-snapshots" / target.snapshot.snapshot_id),
                "Destination": "/opt/subject",
                "RW": False,
                "Propagation": "rprivate",
            }
        ],
        "State": {"Running": True},
    }


def setup(repro):
    r = relocate(repro)
    pending = reserve_t05(r)
    r[1].close()
    store = RecoveryInventory(r[0].directory)
    fake = FakeDocker()
    target = store.inventory(pending.task.task_id).targets[0]
    fake.items["a" * 64] = item(target, store.directory)
    return r, store, fake, pending


def run(store, fake, root, task, apply=False):
    return asyncio.run(RecoveryService(store, root, fake).recover(task, apply=apply))


def test_readonly_then_apply_and_repeat(repro):
    r, store, fake, pending = setup(repro)
    before = store.get(pending.task.task_id)
    report = run(store, fake, r[5], pending.task.task_id)
    assert report.resources[0].state == "present" and report.exit_code() == 2
    assert store.get(pending.task.task_id) == before and not fake.removed
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 0 and report.ledger_reconciled
    assert report.resources[0].state == "removed" and not fake.items
    after = store.get(pending.task.task_id)
    assert after.task.outcome == "outcome_unknown" and after.task.usage == before.task.usage
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 0 and not report.ledger_reconciled
    assert store.get(pending.task.task_id) == after
    store.close()


@pytest.mark.parametrize("mutation", ["image", "label", "snapshot", "mount", "scenario", "id"])
def test_identity_mismatch_never_removes_or_reconciles(repro, mutation):
    r, store, fake, pending = setup(repro)
    i = fake.items["a" * 64]
    if mutation == "image":
        i["Image"] = "sha256:" + "b" * 64
    if mutation == "label":
        i["Config"]["Labels"][PROJECT_LABEL] = "other"
    if mutation == "snapshot":
        i["Config"]["Labels"][SNAPSHOT_LABEL] = "b" * 64
    if mutation == "mount":
        i["Mounts"][0]["RW"] = True
    if mutation == "scenario":
        i["Config"]["Cmd"] = ["--scenario", "pass"]
    if mutation == "id":
        i["Id"] = "not-a-full-container-id"
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 2 and report.resources[0].state == "unknown"
    assert not fake.removed
    assert store.get(pending.task.task_id).task == pending.task
    assert str(r[0].directory) not in report.model_dump_json()
    store.close()


def test_active_owner_refused_before_docker(repro):
    r, store, fake, pending = setup(repro)
    with RepairFence(store.directory, pending.task.task_id):
        report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.error == "OWNER_ACTIVE" and not report.resources and not fake.removed
    store.close()


def test_partial_remove_failure_preserves_pending(repro):
    r, store, fake, pending = setup(repro)
    fake.fail_remove = True
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 2 and report.resources[0].state == "unknown"
    assert store.get(pending.task.task_id).task == pending.task
    store.close()


def test_absent_can_reconcile_without_snapshot_or_image(repro):
    r, store, fake, pending = setup(repro)
    fake.items.clear()
    report = run(store, fake, Path("/nonexistent"), pending.task.task_id, True)
    assert report.exit_code() == 0 and report.outcome == "outcome_unknown"
    store.close()


def test_all_comparison_targets_preflight_before_any_removal(repro):
    r = relocate(repro)
    pending = reserve(r[-1])
    r[1].close()
    store, fake = RecoveryInventory(r[0].directory), FakeDocker()
    inv = store.inventory(pending.task.task_id)
    assert [x.slot for x in inv.targets] == [
        "baseline_wrong_type",
        "baseline_pass",
        "candidate_wrong_type",
        "candidate_pass",
    ]
    for index, target in enumerate(inv.targets):
        cid = str(index + 1) * 64
        fake.items[cid] = item(target, store.directory, cid)
    fake.items["4" * 64]["Config"]["Cmd"] = ["wrong"]
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 2 and not fake.removed and len(report.resources) == 4
    fake.items["4" * 64]["Config"]["Cmd"] = ["--scenario", "pass"]
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 0 and len(fake.removed) == 4
    assert store.get(pending.task.task_id).task.usage == pending.task.usage
    store.close()


def test_cancelled_terminal_task_preserved(repro):
    r = relocate(repro)
    saved = r[0].finish_task(
        r[2].task.task_id, outcome="cancelled", error_code="CANCELLED", **cas(r[2], r[1])
    )
    r[1].close()
    store = RecoveryInventory(r[0].directory)
    report = run(store, FakeDocker(), r[5], saved.task.task_id, True)
    assert report.exit_code() == 0 and report.outcome == "cancelled"
    assert not report.ledger_reconciled and store.get(saved.task.task_id).task == saved.task
    store.close()


def test_verified_terminal_history_not_rewritten(repro):
    from tests.test_repair_comparisons import handles, save_all

    r = relocate(repro)
    c = r[-1]
    pending = reserve(c)
    cursor = save_all(c, pending)
    done = c[0].finalize_comparison(pending.claim, **cas(cursor, r[1]), **handles(c))
    assert done.task.outcome == "candidate_verified"
    r[1].close()
    store = RecoveryInventory(r[0].directory)
    report = run(store, FakeDocker(), r[5], done.task.task_id, True)
    assert report.exit_code() == 0 and report.outcome == "candidate_verified"
    assert not report.ledger_reconciled and store.get(done.task.task_id).task == done.task
    store.close()


def test_new_owner_between_cleanup_and_reconcile_does_not_claim_success(repro, monkeypatch):
    r, store, fake, pending = setup(repro)
    original = store.reconcile_reproduction

    def takeover(task_id, **kwargs):
        with RepairFence(store.directory, task_id):
            return original(task_id, **kwargs)

    monkeypatch.setattr(store, "reconcile_reproduction", takeover)
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 2 and report.requires_reconcile
    assert report.error == "OWNER_ACTIVE" and report.resources[0].state == "removed"
    assert store.get(pending.task.task_id).task == pending.task
    store.close()


def test_container_replacement_after_preflight_is_not_removed(repro, monkeypatch):
    r, store, fake, pending = setup(repro)
    original = fake.command
    scans = 0

    async def replacing(*argv):
        nonlocal scans
        if argv[:2] == ("container", "ls"):
            scans += 1
            if scans == 2:
                replacement = fake.items.pop("a" * 64)
                replacement["Id"] = "b" * 64
                fake.items["b" * 64] = replacement
        return await original(*argv)

    monkeypatch.setattr(fake, "command", replacing)
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.exit_code() == 2 and not fake.removed
    assert store.get(pending.task.task_id).task == pending.task
    store.close()


def test_model_pending_keeps_unknown_reservation_without_docker(repro):
    from agent_workbench.model_gateway.gateway import PreparedCall

    r = relocate(repro)
    # The service must preserve reserved budget when the dead owner's response is lost.
    prepared = PreparedCall(
        request_sha256="a" * 64,
        reservation_sha256="b" * 64,
        input_reserved=80,
        output_reserved=20,
        body=b"",
    )
    from agent_workbench.repair_store.models import RepairTask

    task = RepairTask(
        task_id=str(uuid4()),
        baseline=r[4].ref,
        mode="three_role",
        started_at=r[2].task.started_at,
        budget=r[2].task.budget,
        model_config_sha256="c" * 64,
    )
    with RepairFence(r[0].directory, task.task_id) as fence:
        saved = r[0].create_task(task, fence=fence)
        pending = r[0].reserve_model(
            task.task_id, str(uuid4()), "diagnosis", prepared, **cas(saved, fence)
        )
    r[1].close()
    store = RecoveryInventory(r[0].directory)
    report = run(store, FakeDocker(), Path("/nonexistent"), pending.task.task_id, True)
    assert report.exit_code() == 0 and not report.resources
    assert store.get(pending.task.task_id).task.usage == pending.task.usage
    assert pending.task.usage.reserved_tokens == 100
    store.close()


def test_cli_defaults_to_inspect_and_sanitizes_invalid_input(repro, monkeypatch, capsys):
    from agent_workbench.cli import main
    from agent_workbench.repair_recovery import cli

    r, store, fake, pending = setup(repro)
    monkeypatch.setenv("AWB_STATE_DIR", str(store.directory))
    monkeypatch.setattr(cli, "ROOT", r[5])
    monkeypatch.setattr(
        cli, "RecoveryService", lambda state, root: RecoveryService(state, root, fake)
    )
    assert main(["repair-recovery", "--task-id", pending.task.task_id]) == 2
    assert '"mode":"inspect"' in capsys.readouterr().out and not fake.removed
    assert main(["repair-recovery", "--task-id", pending.task.task_id, "--apply"]) == 0
    assert '"ledger_reconciled":true' in capsys.readouterr().out
    assert main(["repair-recovery", "--task-id", "secret/raw-path"]) == 2
    assert "secret" not in capsys.readouterr().out
    store.close()


def test_stale_revision_after_cleanup_cannot_overwrite_new_ledger(repro, monkeypatch):
    r, store, fake, pending = setup(repro)
    original = store.reconcile_reproduction
    newer = []

    def competing_recovery(task_id, **kwargs):
        newer.append(original(task_id, **kwargs))
        return original(task_id, **kwargs)

    monkeypatch.setattr(store, "reconcile_reproduction", competing_recovery)
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.error == "RECOVERY_UNCONFIRMED" and report.requires_reconcile
    assert not report.ledger_reconciled and store.get(pending.task.task_id).task == newer[0].task
    store.close()


def test_changed_snapshot_retains_container_for_manual_inspection(repro):
    r, store, fake, pending = setup(repro)
    source = r[4].root / "server.py"
    source.chmod(0o600)
    source.write_bytes(b"damaged snapshot with private content")
    report = run(store, fake, r[5], pending.task.task_id, True)
    assert report.error == "RESOURCE_UNVERIFIED" and not fake.removed
    assert store.get(pending.task.task_id).task == pending.task
    assert "private content" not in report.model_dump_json()
    store.close()
