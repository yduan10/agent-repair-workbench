"""Independent P0-06 B1a probes: publication ownership and private DTO boundaries."""

import multiprocessing
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from agent_workbench.candidates.contracts import CandidateError, CandidatePatch
from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore

HEADER = "def lookup_result(count: int, scenario: str) -> dict[str, Any]:\n"


@pytest.fixture
def store(tmp_path):
    value = SnapshotStore(tmp_path / "snapshots")
    yield value
    for root, _directories, files in os.walk(tmp_path, followlinks=False):
        if not Path(root).is_symlink():
            os.chmod(root, 0o700)
        for file in files:
            path = Path(root) / file
            if not path.is_symlink() and path.is_file():
                os.chmod(path, 0o600)


def _publish_worker(root, baseline, candidate_id, sender):
    store = SnapshotStore(root)
    patch = CandidatePatch(
        expected_baseline_hash=baseline.ref.tree_sha256,
        expected_file_hash=baseline.ref.file_sha256,
        replacement=HEADER + '    return {"count": count}\n',
    )
    try:
        value = store.create_candidate(baseline, candidate_id, patch)
        sender.send(("ok", value.ref.file_sha256))
    except CandidateError as exc:
        sender.send((exc.code, None))
    finally:
        sender.close()


def test_independent_processes_publish_one_complete_candidate(store):
    baseline = store.create_baseline(str(uuid4()))
    candidate_id = str(uuid4())
    context = multiprocessing.get_context("fork")
    receivers, workers = [], []
    for _ in range(2):
        receive, send = context.Pipe(duplex=False)
        worker = context.Process(
            target=_publish_worker, args=(store.root, baseline, candidate_id, send)
        )
        worker.start()
        send.close()
        receivers.append(receive)
        workers.append(worker)
    try:
        replies = []
        for receiver in receivers:
            assert receiver.poll(10), "snapshot worker did not produce a bounded reply"
            replies.append(receiver.recv())
        assert sorted(result[0] for result in replies) == ["SNAPSHOT_ID_CONFLICT", "ok"]
        assert sorted(path.name for path in store.root.iterdir()) == sorted(
            [baseline.ref.snapshot_id, candidate_id]
        )
        for worker in workers:
            worker.join(5)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.kill()
            worker.join(5)
        for receiver in receivers:
            receiver.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"snapshot_id": "../outside"},
        {"kind": "candidate"},
        {"file": "other.py"},
        {"file_sha256": "invalid"},
        {"baseline_id": str(uuid4())},
    ],
)
def test_forged_private_ref_is_revalidated_before_read(store, changes):
    baseline = store.create_baseline(str(uuid4()))
    forged = replace(baseline, ref=baseline.ref.model_copy(update=changes))
    with pytest.raises(CandidateError, match="^SNAPSHOT_REQUEST_INVALID$"):
        store.verify(forged)
    assert store.verify(baseline)


def test_candidate_body_remains_inert_and_private_handle_cannot_redirect(store, tmp_path):
    baseline = store.create_baseline(str(uuid4()))
    marker = tmp_path / "MUST_NOT_EXIST"
    body = HEADER + f'    open({str(marker)!r}, "w").write("unexpected execution")\n'
    body += '    return {"count": count}\n'
    candidate = store.create_candidate(
        baseline,
        str(uuid4()),
        CandidatePatch(
            expected_baseline_hash=baseline.ref.tree_sha256,
            expected_file_hash=baseline.ref.file_sha256,
            replacement=body,
        ),
    )
    store.diff(baseline, candidate)
    assert not marker.exists()
    redirected = SnapshotHandle(candidate.ref, baseline.root)
    with pytest.raises(CandidateError, match="^SNAPSHOT_PATH_REJECTED$"):
        store.verify(redirected)
