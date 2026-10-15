"""P1-01b fixed-case write API; never accepts keys, URLs, commands or source files."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_workbench.web_analyses.models import AnalysisRequest
from agent_workbench.web_analyses.service import AnalysisService
from agent_workbench.web_runs.api import body

router = APIRouter(prefix="/api/analysis-runs")


def service(request: Request) -> AnalysisService:
    return cast(AnalysisService, request.app.state.analysis_runs)


@router.get("/catalog")
async def catalog(request: Request) -> Response:
    result = await service(request).catalog()
    return JSONResponse(result.body, status_code=result.status)


@router.post("")
async def create(request: Request) -> Response:
    value = await body(request)
    if isinstance(value, Response):
        return value
    try:
        parsed = AnalysisRequest.model_validate(value)
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).submit(parsed)
    return JSONResponse(result.body, status_code=result.status)


@router.post("/{task_id}/cancel")
async def cancel(task_id: str, request: Request) -> Response:
    value = await body(request)
    if isinstance(value, Response):
        return value
    try:
        if value != {} or str(UUID(task_id)) != task_id:
            raise ValueError
    except ValueError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    result = await service(request).cancel(task_id)
    return JSONResponse(result.body, status_code=result.status)
