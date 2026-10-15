"""Metadata-only evidence for one snapshot/scenario, never a candidate verdict."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from agent_workbench.models import StrictModel

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identity = Annotated[str, Field(pattern=r"^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$")]
Scenario = Literal["pass", "wrong_type"]
StepName = Literal[
    "initialize",
    "schema_before",
    "valid_one",
    "invalid_type",
    "valid_zero",
    "valid_negative",
    "schema_after",
    "alive",
]
STEPS: tuple[StepName, ...] = (
    "initialize",
    "schema_before",
    "valid_one",
    "invalid_type",
    "valid_zero",
    "valid_negative",
    "schema_after",
    "alive",
)


StepCode = Literal[
    "not_run",
    "ok",
    "protocol_mismatch",
    "schema_mismatch",
    "tool_error",
    "structured_missing",
    "result_shape",
    "count_type",
    "count_value",
    "invalid_input_accepted",
    "wrong_error_code",
    "process_exited",
]


class OracleStep(StrictModel):
    name: StepName
    status: Literal["passed", "failed", "not_run"] = "not_run"
    code: StepCode = "not_run"
    result_sha256: Digest | None = None


class OracleReport(StrictModel):
    schema_version: Literal[1] = 1
    attempt_id: Identity
    snapshot_id: Identity
    snapshot_tree_sha256: Digest
    snapshot_file_sha256: Digest
    suite_sha256: Digest
    oracle_sha256: Digest
    image_id: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")] | None = None
    image_source_sha256: Digest | None = None
    scenario: Scenario
    steps: list[OracleStep] = Field(default_factory=lambda: [OracleStep(name=n) for n in STEPS])
    status: Literal["passed", "failed", "inconclusive", "cancelled", "outcome_unknown"] = (
        "inconclusive"
    )
    error: (
        Literal[
            "snapshot_unverified",
            "image_unverified",
            "oracle_unverified",
            "invalid_budget",
            "unsupported_sdk",
            "docker_failure",
            "wire_error",
            "protocol_error",
            "deadline_exceeded",
            "run_cancelled",
            "cleanup_unconfirmed",
            "attach_cleanup_unconfirmed",
        ]
        | None
    ) = None
    snapshot_verified_before: bool = False
    snapshot_verified_after: bool = False
    cleanup: Literal["not_created", "removed", "unconfirmed"] = "not_created"
    stdout_bytes: int = Field(default=0, ge=0)
    stderr_bytes: int = Field(default=0, ge=0)
    frames: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def evidence_consistency(self) -> Self:
        if tuple(s.name for s in self.steps) != STEPS:
            raise ValueError("required_steps_mismatch")
        for step in self.steps:
            expected = (
                "passed"
                if step.code == "ok"
                else ("not_run" if step.code == "not_run" else "failed")
            )
            if step.status != expected:
                raise ValueError("step_status_mismatch")
        if self.status == "passed" and not (
            all(s.status == "passed" for s in self.steps)
            and self.error is None
            and self.snapshot_verified_before
            and self.snapshot_verified_after
            and self.cleanup == "removed"
            and self.image_id
            and self.image_source_sha256
        ):
            raise ValueError("passed_without_complete_evidence")
        return self
