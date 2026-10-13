"""P0-02: application-level provenance, never a claim of raw wire validation."""

from typing import Literal

from pydantic import Field

from agent_workbench.models import Finding, Report, StrictModel

Outcome = Literal[
    "completed",
    "precheck_rejected",
    "unsupported",
    "tool_error",
    "transport_error",
    "protocol_error",
    "outcome_unknown",
]


class Source(StrictModel):
    kind: Literal["mcp_sdk_normalized"] = "mcp_sdk_normalized"
    association: Literal["sdk_dispatch"] = "sdk_dispatch"
    wire_json_integrity: Literal["not_checked"] = "not_checked"
    sdk_version: str = "2.3.0"
    adapter_version: Literal["1"] = "1"
    protocol_version: Literal["2025-11-25"] | None = None
    profile: Literal["contract-fixture", "public-sdk-3644", "isolated-fixture"] | None = None
    config_sha256: str | None = None
    case_sha256: str | None = None
    server_code_sha256: str | None = None
    server_dependencies_sha256: str | None = None
    tool_schema_sha256: str | None = None
    server_revision: str | None = None
    source_tree_sha256: str | None = None


class ContentSummary(StrictModel):
    kind: Literal["text", "image", "audio", "resource", "resource_link", "other"]
    items: int = 0
    text_characters: int = 0


class MCPReport(StrictModel):
    mcp_report_version: Literal[1] = 1
    invocation_id: str
    adapter_outcome: Outcome = "unsupported"
    source: Source = Field(default_factory=Source)
    contract_report: Report | None = None
    preflight_findings: list[Finding] = Field(default_factory=list)
    content_summary: list[ContentSummary] = Field(default_factory=list)
    elapsed_ms: int = 0

    def exit_code(self) -> int:
        if self.adapter_outcome in ("precheck_rejected", "tool_error"):
            return 1
        if self.adapter_outcome == "completed" and self.contract_report is not None:
            return {"passed": 0, "failed": 1, "inconclusive": 2}[self.contract_report.status]
        return 2
