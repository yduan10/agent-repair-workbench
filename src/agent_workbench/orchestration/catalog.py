"""Read-only executable schema catalog; no model or tool invocation endpoint."""

import json
from functools import lru_cache

from fastapi import APIRouter, Response

from agent_workbench.controlled_tools.contracts import TOOL_MODELS
from agent_workbench.orchestration.codec import (
    DIAGNOSIS_ADAPTER,
    REPAIR_ADAPTER,
    VERIFICATION_ADAPTER,
)
from agent_workbench.orchestration.contracts import AnalysisSummary, TaskSpec, TaskState
from agent_workbench.orchestration.policy import ROLE_TOOLS

router = APIRouter()


@lru_cache(maxsize=1)
def catalog_bytes() -> bytes:
    schemas = {
        "diagnosis": DIAGNOSIS_ADAPTER.json_schema(),
        "repair": REPAIR_ADAPTER.json_schema(),
        "verification": VERIFICATION_ADAPTER.json_schema(),
    }
    return json.dumps(
        {
            "catalog_version": 2,
            "cli_runtime_available": True,
            "web_runtime_available": False,
            "roles": [
                {"id": role, "allowed_tools": names, "output_schema": schemas[role]}
                for role, names in ROLE_TOOLS.items()
            ],
            "tools": [
                {
                    "name": model.model_json_schema()["properties"]["tool"]["const"],
                    "request_schema": model.model_json_schema(),
                }
                for model in TOOL_MODELS
            ],
            "task_schema": TaskSpec.model_json_schema(),
            "state_schema": TaskState.model_json_schema(),
            "summary_schema": AnalysisSummary.model_json_schema(),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


@router.get("/api/agent-contracts")
def get_catalog() -> Response:
    return Response(content=catalog_bytes(), media_type="application/json")
