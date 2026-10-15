"""H09 held-out recovery: real SQLite/snapshots, deterministic FakeDocker, no model calls."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_workbench.candidate_execution.docker import SNAPSHOT_LABEL
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.model_gateway.gateway import PreparedCall
from agent_workbench.repair_cases.bindings import validate_baseline_binding
from agent_workbench.repair_cases.profiles import get_profile
from agent_workbench.repair_recovery.inventory import RecoveryInventory
from agent_workbench.repair_store.fencing import RepairFence
from agent_workbench.repair_store.models import RepairTask
from tests.test_repair_comparisons import cas
from tests.test_repair_comparisons import ctx as comparison_context
from tests.test_repair_recovery import FakeDocker, relocate, run, setup
from tests.test_repair_reproductions import repro as reproduction_context


@pytest.fixture
def counter_repro(tmp_path, monkeypatch):
    original = SnapshotStore.create_baseline
    monkeypatch.setattr(
        SnapshotStore,
        "create_baseline",
        lambda self, snapshot_id: original(self, snapshot_id, case_id="counter_offset"),
    )
    comparisons = comparison_context.__wrapped__(tmp_path, SimpleNamespace(param="three_role"))
    context = next(comparisons)
    reproductions = reproduction_context.__wrapped__(context)
    yield next(reproductions)
    with pytest.raises(StopIteration):
        next(reproductions)
    with pytest.raises(StopIteration):
        next(comparisons)


def test_counter_pending_t05_inspect_keeps_exact_profile_and_does_not_write(counter_repro):
    r, store, docker, pending = setup(counter_repro)
    try:
        inventory = store.inventory(pending.task.task_id)
        assert inventory.pending_operation == "reproduction"
        assert len(inventory.targets) == 1
        target = inventory.targets[0]
        assert target.tool == "T05" and target.attempt_id == r[3].attempt_id
        assert target.snapshot == r[4].ref
        assert validate_baseline_binding(target.snapshot).case_id == "counter_offset"
        assert target.snapshot.manifest_sha256 == get_profile("counter_offset").manifest_sha256
        before = store.get(pending.task.task_id)
        report = run(store, docker, r[5], pending.task.task_id)
        assert report.mode == "inspect" and report.resources[0].state == "present"
        assert store.get(pending.task.task_id) == before
        assert docker.removed == [] and len(docker.items) == 1
        assert not report.ledger_reconciled
    finally:
        store.close()


def test_counter_apply_removes_owned_resource_preserves_unknown_and_budget(counter_repro):
    r, store, docker, pending = setup(counter_repro)
    try:
        report = run(store, docker, r[5], pending.task.task_id, True)
        assert report.exit_code() == 0 and report.ledger_reconciled
        assert report.resources[0].state == "removed"
        assert docker.removed == ["a" * 64] and not docker.items
        after = store.get(pending.task.task_id)
        assert after.task.phase == "finished" and after.task.outcome == "outcome_unknown"
        assert after.task.usage == pending.task.usage
        saved = store.get_reproduction(pending.task.task_id, pending.request.request_id)
        assert saved.status == "outcome_unknown" and saved.report is None
        assert not saved.versions_verified_after
        # Repeated explicit recovery does not start a model, T05, T07 or create new identities.
        inventory = store.inventory(pending.task.task_id)
        repeated = run(store, docker, r[5], pending.task.task_id, True)
        assert repeated.exit_code() == 0 and not repeated.ledger_reconciled
        assert store.get(pending.task.task_id) == after
        assert store.inventory(pending.task.task_id) == inventory
        assert docker.removed == ["a" * 64]
    finally:
        store.close()


@pytest.mark.parametrize(
    "mutation", ["cross_profile_label", "cross_profile_source", "source_corrupt"]
)
def test_counter_cross_profile_or_source_mismatch_retains_resource(counter_repro, mutation):
    r, store, docker, pending = setup(counter_repro)
    try:
        if mutation == "cross_profile_label":
            # Even an identical task/name/image cannot authorize deleting another baseline.
            from agent_workbench.mcp_config import canonical, digest

            old = get_profile("output_mismatch")
            docker.items["a" * 64]["Config"]["Labels"][SNAPSHOT_LABEL] = digest(
                canonical({"server.py": old.source_sha256})
            )
        else:
            source = r[4].root / "server.py"
            source.chmod(0o600)
            if mutation == "cross_profile_source":
                from agent_workbench.mcp_config import ROOT

                raw = (ROOT / "examples/analysis/source/server.py").read_bytes()
            else:
                raw = b"damaged synthetic source\n"
            source.write_bytes(raw)
            source.chmod(0o400)
        before = store.get(pending.task.task_id)
        report = run(store, docker, r[5], pending.task.task_id, True)
        assert report.exit_code() == 2 and report.resources[0].state == "unknown"
        assert not report.ledger_reconciled and not docker.removed and len(docker.items) == 1
        assert store.get(pending.task.task_id) == before
        assert before.task.usage == pending.task.usage
        assert str(store.directory) not in report.model_dump_json()
        assert "damaged synthetic" not in report.model_dump_json()
    finally:
        store.close()


def test_counter_lost_model_reservation_retained_without_execution(counter_repro):
    r = relocate(counter_repro)
    prepared = PreparedCall(
        request_sha256="a" * 64,
        reservation_sha256="b" * 64,
        input_reserved=80,
        output_reserved=20,
        body=b"",
    )
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
            task.task_id,
            str(uuid4()),
            "diagnosis",
            prepared,
            **cas(saved, fence),
        )
    r[1].close()
    store, docker = RecoveryInventory(r[0].directory), FakeDocker()
    try:
        assert validate_baseline_binding(pending.task.baseline).case_id == "counter_offset"
        report = run(store, docker, r[5], task.task_id, True)
        after = store.get(task.task_id)
        assert report.exit_code() == 0 and report.outcome == "outcome_unknown"
        assert after.task.usage == pending.task.usage
        assert after.task.usage.reserved_tokens == 100
        assert after.task.phase == "finished" and not report.resources
        assert not docker.removed and not docker.items
        assert store.inventory(task.task_id).targets == ()
    finally:
        store.close()
