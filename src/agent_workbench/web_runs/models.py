"""Versioned fixed request catalog: no caller-selected execution parameters."""

from typing import Literal
from uuid import UUID

from pydantic import field_validator

from agent_workbench.mcp_config import CallCase, canonical, digest
from agent_workbench.models import StrictModel
from agent_workbench.runner.models import SandboxConfig

WebScenario = Literal["pass", "tool_error", "timeout", "response_lost"]
CASE = CallCase(case_id="synthetic-lookup", tool="lookup", arguments={"id": 1})


class ReproductionRequest(StrictModel):
    request_id: str
    scenario: WebScenario

    @field_validator("request_id")
    @classmethod
    def canonical_uuid(cls, value: str) -> str:
        if str(UUID(value)) != value:
            raise ValueError("invalid_request_id")
        return value

    def config(self) -> SandboxConfig:
        return SandboxConfig(scenario=self.scenario, seed=0, lifetime=45)

    def fingerprints(self) -> tuple[str, str, str]:
        config_hash = digest(canonical(self.config().model_dump()))
        case_hash = digest(canonical(CASE.model_dump()))
        return (
            config_hash,
            case_hash,
            digest(
                canonical(
                    {
                        "version": 1,
                        "config_sha256": config_hash,
                        "case_sha256": case_hash,
                    }
                )
            ),
        )
