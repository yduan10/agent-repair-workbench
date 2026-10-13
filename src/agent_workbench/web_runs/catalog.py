"""Read-only readiness: no database initialization, image build or fixture execution."""

from pathlib import Path
from typing import Literal

import anyio

from agent_workbench.run_store.models import StoreError
from agent_workbench.runner.docker import DockerControl, DockerFailure
from agent_workbench.runner.service import verified_image
from agent_workbench.web_runs.fencing import locking_supported
from agent_workbench.web_runs.store import WebRunStore

Reason = Literal[
    "store_not_initialized",
    "schema_incompatible",
    "store_unavailable",
    "locking_unavailable",
    "image_not_prepared",
    "docker_unavailable",
    "runner_busy",
]
CASES = [
    {
        "id": "pass",
        "title": "正常调用",
        "description": "合成 lookup 返回符合契约的数据。",
        "expected": "通过；执行资源回收。",
    },
    {
        "id": "tool_error",
        "title": "工具错误",
        "description": "合成工具显式返回错误。",
        "expected": "失败；不会将工具错误当作成功。",
    },
    {
        "id": "timeout",
        "title": "调用超时",
        "description": "合成调用在发送后不及时回应。",
        "expected": "结果未知；清理资源，不自动重试。",
    },
    {
        "id": "response_lost",
        "title": "响应丢失",
        "description": "合成调用发生后丢失回应。",
        "expected": "结果未知；不能推断调用未执行。",
    },
]


def state_snapshot(directory: Path) -> tuple[Reason | None, str | None]:
    store = WebRunStore(directory)
    try:
        active = store.active_id()
        return ("runner_busy" if active else None), active
    except StoreError as error:
        return (
            "store_not_initialized"
            if error.code == "not_found"
            else "schema_incompatible"
            if error.code == "schema_incompatible"
            else "store_unavailable"
        ), None
    finally:
        store.close()


async def prepared(image_root: Path | None = None) -> Reason | None:
    if not locking_supported():
        return "locking_unavailable"
    try:
        manifest = await anyio.to_thread.run_sync(
            lambda: verified_image() if image_root is None else verified_image(image_root)
        )
    except (ValueError, OSError, RecursionError):
        return "image_not_prepared"
    try:
        with anyio.fail_after(8):
            control = await DockerControl.connect()
            actual = await control.command(
                "image", "inspect", manifest.image_id, "--format", "{{.Id}}"
            )
        if actual.decode("ascii").strip() != manifest.image_id:
            return "image_not_prepared"
    except (DockerFailure, OSError, ValueError, TimeoutError):
        return "docker_unavailable"
    return None


async def catalog(directory: Path, image_root: Path | None = None) -> dict[str, object]:
    reason, active = await anyio.to_thread.run_sync(state_snapshot, directory)
    if reason is None:
        reason = await prepared(image_root)
    return {
        "version": 1,
        "cases": CASES,
        "ready": reason is None,
        "reason": reason,
        "active_run_id": active,
    }
