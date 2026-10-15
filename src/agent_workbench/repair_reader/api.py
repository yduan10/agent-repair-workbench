"""Bounded local GET endpoints. No model, oracle execution or migration is called."""

import asyncio
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.mcp_config import ROOT, canonical
from agent_workbench.orchestration.contracts import Contract
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import StoreError

from .reader import RepairReader

router = APIRouter(prefix="/api/repairs")
Operation = Literal["list", "detail", "diff", "comparison"]
MAX_RESPONSE = 524288


def _read(operation: Operation, task_id: str, item_id: str, limit: int) -> Response:
    reader = RepairReader(state_directory(), ROOT)
    try:
        value: Contract
        if operation == "list":
            value = reader.list(limit)
        elif operation == "detail":
            value = reader.detail(task_id)
        elif operation == "diff":
            value = reader.diff(task_id, item_id)
        else:
            value = reader.comparison(task_id, item_id)
        raw = canonical(value.model_dump(mode="json"))
        if len(raw) > MAX_RESPONSE:
            return JSONResponse({"error": "response_limit"}, status_code=413)
        return Response(content=raw, media_type="application/json")
    except StoreError as error:
        if error.code in (
            "not_found",
            "repair_not_found",
            "candidate_not_found",
            "comparison_not_found",
        ):
            return JSONResponse({"error": "repair_record_not_found"}, status_code=404)
        code = (
            error.code
            if error.code in ("schema_incompatible", "store_corrupt")
            else "store_unavailable"
        )
        return JSONResponse({"error": code}, status_code=503)
    except (CandidateError, OSError):
        return JSONResponse({"error": "artifact_unavailable"}, status_code=409)
    except Exception:
        return JSONResponse({"error": "repair_read_unavailable"}, status_code=503)
    finally:
        reader.close()


def _valid_id(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


async def _dispatch(
    request: Request, operation: Operation, task_id: str = "", item_id: str = "", limit: int = 20
) -> Response:
    gate: asyncio.Semaphore = request.app.state.repair_reads
    if gate.locked():
        return JSONResponse({"error": "repair_reads_busy"}, status_code=429)
    await gate.acquire()

    async def execute() -> Response:
        try:
            return await asyncio.to_thread(_read, operation, task_id, item_id, limit)
        finally:
            gate.release()

    worker = asyncio.create_task(execute())
    request.app.state.workers.add(worker)
    worker.add_done_callback(request.app.state.workers.discard)
    # Cancelling the HTTP waiter does not release the slot before disk reads finish.
    return await asyncio.shield(worker)


@router.get("")
async def listing(request: Request) -> Response:
    values = request.query_params.getlist("limit")
    value = values[0] if values else "20"
    if (
        set(request.query_params) - {"limit"}
        or len(values) > 1
        or not value.isascii()
        or not value.isdigit()
        or len(value) > 2
        or not 1 <= int(value) <= 50
    ):
        return JSONResponse({"error": "invalid_limit"}, status_code=400)
    return await _dispatch(request, "list", limit=int(value))


@router.get("/{task_id}")
async def detail(task_id: str, request: Request) -> Response:
    if not _valid_id(task_id) or request.query_params:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    return await _dispatch(request, "detail", task_id)


@router.get("/{task_id}/candidates/{candidate_id}/diff")
async def diff(task_id: str, candidate_id: str, request: Request) -> Response:
    if not all(_valid_id(value) for value in (task_id, candidate_id)) or request.query_params:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    return await _dispatch(request, "diff", task_id, candidate_id)


@router.get("/{task_id}/comparisons/{comparison_id}")
async def comparison(task_id: str, comparison_id: str, request: Request) -> Response:
    if not all(_valid_id(value) for value in (task_id, comparison_id)) or request.query_params:
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    return await _dispatch(request, "comparison", task_id, comparison_id)
