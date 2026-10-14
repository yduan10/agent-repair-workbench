"""Safe analysis summaries only; never starts a graph, model or execution."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import StoreError

router = APIRouter(prefix="/api/analyses")


def _read(task_id: str | None, limit: int) -> Response:
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
