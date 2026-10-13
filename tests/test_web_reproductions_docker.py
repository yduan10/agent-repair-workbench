"""W09: opt-in real Docker for all four reviewed Web scenarios, isolated state."""

import os
from pathlib import Path
from uuid import uuid4

import anyio
import pytest

from agent_workbench.web_runs.models import ReproductionRequest
from agent_workbench.web_runs.service import ReproductionService
from agent_workbench.web_runs.store import WebRunStore

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("AWB_DOCKER_TESTS") != "1",
        reason="explicitly prepared Docker image required",
    ),
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "scenario,status",
    [
        ("pass", "succeeded"),
        ("tool_error", "failed"),
        ("timeout", "outcome_unknown"),
        ("response_lost", "outcome_unknown"),
    ],
)
async def test_real_web_scenario_persists_and_reclaims(tmp_path, scenario, status):
    store = WebRunStore(tmp_path / "state")
    store.initialize()
    image_root = os.environ.get("AWB_TEST_IMAGE_ROOT")
    owner = ReproductionService(
        store.directory, image_root=Path(image_root) if image_root else None
    )
    req = ReproductionRequest(request_id=str(uuid4()), scenario=scenario)
    try:
        accepted = await owner.submit(req)
        assert accepted.status == 202, accepted.body
        with anyio.fail_after(50):
            while owner.tasks:
                await anyio.sleep(0.05)
        view = store.detail(req.request_id).run
        assert view.status == status
        report = store.report(req.request_id)
        assert report.record_id == req.request_id and report.run_id == view.attempt_id
        assert report.execution.cleanup == "removed"
        assert store.active_id() is None
        assert (await owner.submit(req)).status == 200
    finally:
        await owner.close()
        store.close()
