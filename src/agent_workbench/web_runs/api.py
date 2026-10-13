"""Only fixed reviewed reproductions can cross the local HTTP write boundary."""

import asyncio
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_workbench.checker import parse_json_bytes
from agent_workbench.web_runs.catalog import catalog
from agent_workbench.web_runs.models import ReproductionRequest
from agent_workbench.web_runs.service import ReproductionService

router = APIRouter(prefix="/api/reproductions")


def service(request: Request) -> ReproductionService:
    return cast(ReproductionService, request.app.state.reproductions)


async def body(request: Request) -> object | Response:
    if request.headers.get("origin") not in request.app.state.local_origins:
        return JSONResponse({"error": "origin_forbidden"}, status_code=403)
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        return JSONResponse({"error": "unsupported_media_type"}, status_code=415)
    raw = bytearray()
    try:
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > 4096:
                    return JSONResponse({"error": "input_limit_exceeded"}, status_code=413)
                raw.extend(chunk)
        return parse_json_bytes(bytes(raw))
    except TimeoutError:
        return JSONResponse({"error": "request_timeout"}, status_code=408)
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)


@router.get("/catalog")
async def get_catalog(request: Request) -> Response:
    owner = service(request)
    return JSONResponse(await catalog(owner.directory, owner.image_root))


@router.post("")
async def create(request: Request) -> Response:
    value = await body(request)
    if isinstance(value, Response):
        return value
    try:
        parsed = ReproductionRequest.model_validate(value)
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).submit(parsed)
    return JSONResponse(result.body, status_code=result.status)


@router.post("/{run_id}/cancel")
async def cancel(run_id: str, request: Request) -> Response:
    value = await body(request)
    if isinstance(value, Response):
        return value
    try:
        if value != {} or str(UUID(run_id)) != run_id:
            raise ValueError
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).cancel(run_id)
    return JSONResponse(result.body, status_code=result.status)
