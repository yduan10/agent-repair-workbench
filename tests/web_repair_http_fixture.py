"""Test-only multiworker app. No model network calls or containers; never used by product."""

import asyncio
import json
import os
from pathlib import Path

from agent_workbench import api
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.model_gateway.gateway import PreparedCall, Reply
from agent_workbench.web_repairs import catalog
from agent_workbench.web_repairs.service import RepairService
from tests.test_web_analysis_service import config


class Model:
    config_sha256 = "a" * 64

    def prompt(self, role):
        return "synthetic bounded HTTP test"

    def prepare(self, role, messages, output_cap):
        self.task_id = json.loads(messages[1]["content"])["task_id"]
        raw = canonical(messages)
        return PreparedCall(raw, digest(raw), 10000, output_cap, "b" * 64)

    async def send(self, request, timeout):
        fd = os.open(os.environ["B2_TEST_CALLS"], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(
                fd, (json.dumps({"task_id": self.task_id, "pid": os.getpid()}) + "\n").encode()
            )
        finally:
            os.close(fd)
        await asyncio.sleep(30)
        return Reply(error="MODEL_TIMEOUT")


def factory():
    async def prepared(root):
        return None

    catalog.preflight = prepared
    api.RepairService = lambda directory: RepairService(
        directory,
        image_root=Path(os.environ["B2_TEST_IMAGE"]),
        config_loader=config,
        adapter_factory=lambda _: Model(),
    )
    app = api.create_app()

    @app.get("/api/test-worker")
    async def worker():
        return {"pid": os.getpid()}

    return app
