"""Versioned wire contracts; raw values never appear in report models."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from agent_workbench import __version__

Name = Annotated[str, Field(min_length=1, max_length=128)]
CheckStatus = Literal["passed", "failed", "not_checked", "skipped"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Tool(StrictModel):
    name: Name
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def reject_explicit_null(self) -> Self:
        if "output_schema" in self.model_fields_set and self.output_schema is None:
            raise ValueError("output_schema must be omitted or an object")
        return self


class Call(StrictModel):
    call_id: Name
    tool_name: Name
    arguments: dict[str, JsonValue]


class Result(StrictModel):
    call_id: Name
    is_error: bool
    structured_content: JsonValue = None


class Evidence(StrictModel):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    tool: Tool
    call: Call
    result: Result | None = None

    @model_validator(mode="after")
    def reject_explicit_null(self) -> Self:
        if "result" in self.model_fields_set and self.result is None:
            raise ValueError("result must be omitted or an object")
        return self


class Finding(StrictModel):
    code: str
    phase: str
    instance_path: str = ""
    schema_path: str = ""


class Checks(StrictModel):
    input: CheckStatus = "not_checked"
    output: CheckStatus = "not_checked"


class Report(StrictModel):
    schema_version: Literal[1] = 1
    checker_version: str = __version__
    evidence_sha256: str | None = None
    status: Literal["passed", "failed", "inconclusive"] = "inconclusive"
    checks: Checks = Field(default_factory=Checks)
    findings: list[Finding] = Field(default_factory=list)
    findings_truncated: bool = False


def incomplete(code: str, digest: str | None = None) -> Report:
    return Report(evidence_sha256=digest, findings=[Finding(code=code, phase="document")])
