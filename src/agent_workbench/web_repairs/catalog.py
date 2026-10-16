"""Host-owned choices and readiness checks; never accepts browser infrastructure."""

import asyncio
from pathlib import Path

from agent_workbench.candidate_execution.docker import verified_image
from agent_workbench.candidate_execution.oracle import verify_oracle
from agent_workbench.run_store.models import StoreError
from agent_workbench.runner.docker import DockerControl

CASES = [
    {"id": "output_mismatch", "label": "返回值类型错误"},
    {"id": "counter_offset", "label": "计数值偏移"},
]
MODES = [{"id": "single_role", "label": "单角色"}, {"id": "three_role", "label": "三角色"}]


def image_ready(root: Path) -> bool:
    try:
        verified_image(root)
        return verify_oracle()
    except (OSError, ValueError):
        return False


async def preflight(root: Path) -> None:
    try:
        async with asyncio.timeout(8):
            manifest = verified_image(root)
            if not verify_oracle():
                raise ValueError
            control = await DockerControl.connect()
            actual = await control.command(
                "image", "inspect", manifest.image_id, "--format", "{{.Id}}"
            )
            if actual.decode("ascii").strip() != manifest.image_id:
                raise ValueError
    except Exception:
        raise StoreError("image_unavailable") from None
