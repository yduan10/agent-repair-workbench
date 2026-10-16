"""Strict local write API for two fixed repair cases; no arbitrary execution input."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_workbench.web_runs.api import body as read_body

from .models import RepairRequest
from .service import RepairService

router = APIRouter(prefix="/api/repair-runs")


def service(request: Request) -> RepairService:
    return cast(RepairService, request.app.state.repair_runs)


async def body(request: Request) -> object | Response:
    if request.headers.get("origin") not in request.app.state.local_origins:
        return JSONResponse({"error": "forbidden_origin"}, status_code=403)
    return await read_body(request)


def valid_id(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


@router.get("/catalog")
async def catalog(request: Request) -> Response:
    result = await service(request).catalog()
    return JSONResponse(result.body, status_code=result.status)


@router.get("/{task_id}")
async def get(task_id: str, request: Request) -> Response:
    if not valid_id(task_id):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).read(task_id)
    return JSONResponse(result.body, status_code=result.status)


@router.post("")
async def create(request: Request) -> Response:
    value = await body(request)
    if isinstance(value, Response):
        return value
    try:
        parsed = RepairRequest.model_validate(value)
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).submit(parsed)
    return JSONResponse(result.body, status_code=result.status)


@router.post("/{task_id}/cancel")
async def cancel(task_id: str, request: Request) -> Response:
    value = await body(request)
    if isinstance(value, Response):
        return value
    if value != {} or not valid_id(task_id):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).read(task_id, cancel=True)
    return JSONResponse(result.body, status_code=result.status)


@router.get("/{task_id}/events")
async def events(task_id: str, request: Request) -> Response:
    if not valid_id(task_id) or request.query_params:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).events(task_id)
    return JSONResponse(result.body, status_code=result.status)
