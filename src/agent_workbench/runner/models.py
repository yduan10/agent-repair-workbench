"""Reviewed configuration and metadata-only execution evidence."""

from typing import Literal

from pydantic import Field

from agent_workbench.mcp_models import MCPReport
from agent_workbench.models import StrictModel

Scenario = Literal[
    "pass",
    "tool_error",
    "timeout",
    "response_lost",
    "duplicate_result",
    "crash_before_call",
    "crash_during_call",
    "crash_before_result",
    "stdout_flood",
    "stderr_flood",
    "stdout_total_flood",
    "pid_limit",
    "spawn_child",
    "oom",
    "cpu_spin",
    "policy_probe",
]


class SandboxConfig(StrictModel):
    profile: Literal["isolated-fixture"] = "isolated-fixture"
    scenario: Scenario = "pass"
    seed: int = Field(default=0, ge=0, le=2147483647)
    lifetime: int = Field(default=45, ge=5, le=45)


class ImageManifest(StrictModel):
    image_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    base_digest: Literal[
        "python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
    ]


class ExecutionEvidence(StrictModel):
    image_id: str | None = None
    source_sha256: str | None = None
    scenario: Scenario | None = None
    seed: int | None = None
    policy: Literal["offline-readonly-v1"] = "offline-readonly-v1"
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    frames: int = 0
    error: str | None = None
    cleanup: Literal["not_created", "removed", "unconfirmed"] = "not_created"
    container_exit_code: int | None = None
    oom_killed: bool = False


class SandboxReport(StrictModel):
    sandbox_report_version: Literal[1] = 1
    run_id: str
    record_id: str | None = None
    mcp: MCPReport
    execution: ExecutionEvidence = Field(default_factory=ExecutionEvidence)

    def exit_code(self) -> int:
        if self.execution.error or self.execution.cleanup == "unconfirmed":
            return 2
        return self.mcp.exit_code()
