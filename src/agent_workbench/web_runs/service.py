"""Lifespan-owned accept/execute tasks; HTTP disconnect cannot revoke admission."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import anyio

from agent_workbench.mcp_config import canonical
from agent_workbench.run_store.execution import terminal_status
from agent_workbench.run_store.models import Claim, RunView, StoreError
from agent_workbench.runner.models import SandboxReport
from agent_workbench.runner.service import run_sandbox
from agent_workbench.web_runs import catalog
from agent_workbench.web_runs.fencing import OwnerFence
from agent_workbench.web_runs.models import CASE, ReproductionRequest
from agent_workbench.web_runs.store import WebRunStore

T = TypeVar("T")


@dataclass(frozen=True)
class Admission:
    status: int
    body: dict[str, object]


def failure(code: str) -> Admission:
    status = {
        "request_conflict": 409,
        "request_gone": 410,
        "runner_busy": 429,
        "web_run_not_found": 404,
    }.get(code, 503)
    allowed = {
        "request_conflict",
        "request_gone",
        "runner_busy",
        "web_run_not_found",
        "store_not_initialized",
        "schema_incompatible",
        "store_unavailable",
        "locking_unavailable",
        "image_not_prepared",
        "docker_unavailable",
        "service_stopping",
    }
    return Admission(status, {"error": code if code in allowed else "store_unavailable"})


class ReproductionService:
    def __init__(self, directory: Path, *, image_root: Path | None = None) -> None:
        self.directory = directory
        self.image_root = image_root
        self.tasks: set[asyncio.Task[None]] = set()
        self.scopes: set[anyio.CancelScope] = set()
        self.stopping = False

    async def database(self, operation: Callable[[WebRunStore], T]) -> T:
        def invoke() -> T:
            store = WebRunStore(self.directory)
            try:
                return operation(store)
            finally:
                store.close()

        return await anyio.to_thread.run_sync(invoke)

    async def submit(self, request: ReproductionRequest) -> Admission:
        if self.stopping:
            return failure("service_stopping")
        response: asyncio.Future[Admission] = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(self._serve(request, response))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        # Shield the response Future as well as the separate owner task.
        return await asyncio.shield(response)

    async def _serve(
        self, request: ReproductionRequest, response: asyncio.Future[Admission]
    ) -> None:
        fence = OwnerFence(self.directory)
        try:
            existing = await self.database(lambda store: store.existing(request))
            if existing is not None:
                response.set_result(Admission(200, {"run": existing.model_dump(), "reused": True}))
                return
            try:
                fence.acquire()
            except StoreError:
                # A concurrent owner may just have committed the same request.
                existing = await self.database(lambda store: store.existing(request))
                if existing is not None:
                    response.set_result(
                        Admission(200, {"run": existing.model_dump(), "reused": True})
                    )
                    return
                raise
            if not await self.database(lambda store: store.release_safe(fence)):
                raise StoreError("runner_busy")
            reason = await catalog.prepared(self.image_root)
            if reason is not None:
                raise StoreError(reason)
            if self.stopping:
                raise StoreError("service_stopping")
            accepted = await self.database(lambda store: store.admit(request, fence))
            if isinstance(accepted, RunView):
                response.set_result(Admission(200, {"run": accepted.model_dump(), "reused": True}))
                return
            # Owner task already registered and fence retained before HTTP can see 202.
            response.set_result(Admission(202, {"run": accepted.run.model_dump(), "reused": False}))
            await self._execute(request, accepted, fence)
        except StoreError as error:
            if not response.done():
                response.set_result(
                    failure("store_not_initialized" if error.code == "not_found" else error.code)
                )
        except Exception:
            # Durable running record/slot remains conservative if execution or save failed.
            if not response.done():
                response.set_result(failure("store_unavailable"))
        finally:
            fence.close()
            if not response.done():
                response.set_result(failure("service_stopping"))

    async def _execute(self, request: ReproductionRequest, claim: Claim, fence: OwnerFence) -> None:
        assert claim.run.attempt_id is not None
        report: SandboxReport | None = None
        with anyio.CancelScope() as scope:
            self.scopes.add(scope)
            try:
                if self.stopping or await self.database(
                    lambda store: store.cancellation_requested(request.request_id)
                ):
                    scope.cancel()

                async def watch_cancel() -> None:
                    while True:
                        await anyio.sleep(0.1)
                        if await self.database(
                            lambda store: store.cancellation_requested(request.request_id)
                        ):
                            scope.cancel()
                            return

                async with anyio.create_task_group() as group:
                    group.start_soon(watch_cancel)
                    report = await run_sandbox(
                        canonical(request.config().model_dump()),
                        canonical(CASE.model_dump()),
                        run_id=claim.run.attempt_id,
                        image_root=self.image_root,
                    )
                    group.cancel_scope.cancel()
            finally:
                self.scopes.discard(scope)
        if report is None:
            # A failure outside runner cannot establish whether a call was sent.
            return
        report.record_id = request.request_id
        # Cancelling an HTTP request or the execution scope cannot cancel this commit.
        with anyio.CancelScope(shield=True):
            await self.database(
                lambda store: store.finish(
                    request.request_id,
                    claim.run.attempt_id or "",
                    claim.token,
                    expected_version=claim.run.version,
                    status=terminal_status(report),
                    report=report,
                    executor_state="absent"
                    if report.execution.cleanup != "unconfirmed"
                    else "unavailable",
                )
            )
            await self.database(lambda store: store.release_safe(fence))

    async def cancel(self, run_id: str) -> Admission:
        try:
            requested = await self.database(lambda store: store.request_cancel(run_id))
            return Admission(
                202 if requested else 200,
                {
                    "run_id": run_id,
                    "status": "cancel_requested" if requested else "already_finished",
                },
            )
        except StoreError as error:
            return failure("web_run_not_found" if error.code == "not_found" else error.code)

    async def close(self) -> None:
        self.stopping = True
        for scope in tuple(self.scopes):
            scope.cancel()
        # Runner enforces 30s execution + bounded cleanup; admission probe <=8s.
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
