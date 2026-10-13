"""Read-only local run metadata. No lease token or execution endpoint crosses HTTP."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_workbench.mcp_config import canonical
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.store import RunStore

router = APIRouter()


def _read(operation: str, run_id: str | None = None, limit: int = 50) -> Response:
    store = RunStore(state_directory())
    try:
        if operation == "list":
            return JSONResponse(
                {"runs": [run.model_dump(mode="json") for run in store.list_runs(limit)]}
            )
        assert run_id is not None
        if operation == "detail":
            return JSONResponse(store.detail(run_id).model_dump(mode="json"))
        report = store.report(run_id)
        return Response(
            content=canonical(report.model_dump(mode="json")),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="run-{run_id}.json"'},
        )
    except StoreError as error:
        status = 404 if error.code in ("not_found", "run_not_found", "report_not_found") else 503
        return JSONResponse({"error": error.code}, status_code=status)
    finally:
        store.close()


def _valid_id(run_id: str) -> bool:
    try:
        return str(UUID(run_id)) == run_id
    except ValueError:
        return False


@router.get("/api/runs")
async def list_runs(request: Request) -> Response:
    value = request.query_params.get("limit", "50")
    if not value.isascii() or not value.isdigit() or len(value) > 3 or not 1 <= int(value) <= 100:
        return JSONResponse({"error": "invalid_limit"}, status_code=400)
    return await asyncio.to_thread(_read, "list", None, int(value))


@router.get("/api/runs/{run_id}")
async def detail(run_id: str) -> Response:
    if not _valid_id(run_id):
        return JSONResponse({"error": "invalid_run_id"}, status_code=400)
    return await asyncio.to_thread(_read, "detail", run_id)


@router.get("/api/runs/{run_id}/report")
async def report(run_id: str) -> Response:
    if not _valid_id(run_id):
        return JSONResponse({"error": "invalid_run_id"}, status_code=400)
    return await asyncio.to_thread(_read, "report", run_id)
