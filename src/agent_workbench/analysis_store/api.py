"""Safe analysis summaries only; never starts a graph, model or execution."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import StoreError

router = APIRouter(prefix="/api/analyses")


def _read(task_id: str | None, limit: int, *, evidence: bool = False) -> Response:
    store = AnalysisStore(state_directory())
    try:
        if task_id is None:
            return JSONResponse(
                {
                    "analyses": [
                        {"summary": item.summary.model_dump(mode="json"), "sha256": item.sha256}
                        for item in store.list(limit)
                    ]
                }
            )
        saved, events = store.detail(task_id)
        if evidence:
            from agent_workbench.analysis_store.evidence import resolve_evidence

            content = resolve_evidence(saved.summary, saved.sha256)
            return JSONResponse(content.model_dump(mode="json"))
        return JSONResponse(
            {
                "summary": saved.summary.model_dump(mode="json"),
                "sha256": saved.sha256,
                "events": [item.model_dump(mode="json") for item in events],
            }
        )
    except StoreError as error:
        if error.code in ("not_found", "analysis_not_found"):
            return JSONResponse({"error": "analysis_not_found"}, status_code=404)
        code = (
            error.code
            if error.code in ("analysis_corrupt", "schema_incompatible")
            else "store_unavailable"
        )
        return JSONResponse({"error": code}, status_code=503)
    finally:
        store.close()


@router.get("")
async def listing(request: Request) -> Response:
    values = request.query_params.getlist("limit")
    value = values[0] if values else "20"
    if (
        len(values) > 1
        or not value.isascii()
        or not value.isdigit()
        or len(value) > 2
        or not 1 <= int(value) <= 50
    ):
        return JSONResponse({"error": "invalid_limit"}, status_code=400)
    return await asyncio.to_thread(_read, None, int(value))


@router.get("/{task_id}")
async def detail(task_id: str) -> Response:
    try:
        if str(UUID(task_id)) != task_id:
            raise ValueError
    except ValueError:
        return JSONResponse({"error": "invalid_task_id"}, status_code=400)
    return await asyncio.to_thread(_read, task_id, 20)


@router.get("/{task_id}/evidence")
async def evidence(task_id: str, request: Request) -> Response:
    try:
        if str(UUID(task_id)) != task_id:
            raise ValueError
    except ValueError:
        return JSONResponse({"error": "invalid_task_id"}, status_code=400)
    # Reconstruction uses the bounded checker; share its single local execution slot.
    gate: asyncio.Semaphore = request.app.state.gate
    if gate.locked():
        return JSONResponse({"error": "evidence_busy"}, status_code=429)
    await gate.acquire()

    async def execute() -> Response:
        try:
            return await asyncio.to_thread(_read, task_id, 20, evidence=True)
        finally:
            gate.release()

    worker = asyncio.create_task(execute())
    request.app.state.workers.add(worker)
    worker.add_done_callback(request.app.state.workers.discard)
    return await asyncio.shield(worker)
