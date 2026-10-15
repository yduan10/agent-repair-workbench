"""Resolve saved references only against hash-matched reviewed public case content."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, ValidationError

from agent_workbench.controlled_tools.contracts import ReadSource
from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.models import Checks
from agent_workbench.orchestration.contracts import (
    AnalysisSummary,
    Budget,
    Contract,
    Digest,
    EvidenceRef,
    Identifier,
)

UNAVAILABLE = "仅保留引用，具体内容未保存或当前版本不匹配"


class SafeFinding(Contract):
    code: Annotated[str, Field(max_length=128)]
    path: Annotated[str, Field(max_length=1024)]


class ReadableReport(Contract):
    status: Literal["passed", "failed", "inconclusive"]
    input: Literal["passed", "failed", "not_checked", "skipped"]
    output: Literal["passed", "failed", "not_checked", "skipped"]


class ReadableSource(Contract):
    path: Literal["source/server.py"] = "source/server.py"
    start_line: Literal[107] = 107
    end_line: Literal[110] = 110
    text: Annotated[str, Field(max_length=16384)]


class ReadableSchemas(Contract):
    tool_name: Literal["lookup"] = "lookup"
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue] | None


class EvidenceContent(Contract):
    kind: Literal["report", "source", "contract", "unavailable"]
    title: Annotated[str, Field(max_length=120)]
    description: Annotated[str, Field(max_length=800)]
    findings: Annotated[tuple[SafeFinding, ...], Field(max_length=50)] = ()
    report: ReadableReport | None = None
    source: ReadableSource | None = None
    schemas: ReadableSchemas | None = None


class EvidenceItem(EvidenceContent):
    ref: EvidenceRef


class EvidenceResponse(Contract):
    schema_version: Literal[1] = 1
    task_id: Identifier
    summary_sha256: Digest
    evidence: Annotated[tuple[EvidenceItem, ...], Field(max_length=32)]


def _public_content(task_id: str, root: Path | None) -> dict[str, EvidenceContent]:
    """Reconstruct exact original registry payloads; source text is a verified supplement."""
    result: dict[str, EvidenceContent] = {}
    for case in ("output_mismatch", "passing"):
        try:
            registry = load_case(
                case,
                task_id=task_id,
                intent="check_only",
                budget=Budget(total_tokens=1000, output_tokens=100),
                root=root,
            )
            report = registry.initial_report()
            payload = {
                "summary": report.model_dump(mode="json", exclude={"findings"}),
                "findings": [finding.model_dump(mode="json") for finding in report.findings],
                "events": [],
            }
            checks: Checks = report.checks
            result[digest(canonical(payload))] = EvidenceContent(
                kind="report",
                title="工具调用契约检查",
                description="与保存引用精确匹配的公开案例检查；仅包含规则和字段位置。",
                findings=tuple(
                    SafeFinding(code=f.code, path=f.instance_path) for f in report.findings
                ),
                report=ReadableReport(
                    status=report.status, input=checks.input, output=checks.output
                ),
            )
            contract = registry.contract()
            payload = {
                "summary": {"tool": "lookup", "contract_revision": registry.contract_revision},
                "findings": [],
                "events": [],
            }
            schemas = ReadableSchemas.model_validate(
                {
                    "tool_name": contract["name"],
                    "input_schema": contract["input_schema"],
                    "output_schema": contract.get("output_schema"),
                }
            )
            result[digest(canonical(payload))] = EvidenceContent(
                kind="contract",
                title="lookup 输入与输出契约",
                description="与保存引用中的契约版本匹配的公开 schema；不包含调用参数或结果值。",
                schemas=schemas,
            )
            request = next(
                item for item in registry.templates("diagnosis") if isinstance(item, ReadSource)
            )
            # Do not widen the reader even if a future approved manifest changes its range.
            if (request.relative_path, request.start_line, request.end_line) != (
                "source/server.py",
                107,
                110,
            ):
                continue
            source = registry.source(request)  # no-follow open, full-file hash, bounded read
            payload = {
                "summary": {key: value for key, value in source.items() if key != "text"},
                "findings": [],
                "events": [],
            }
            result[digest(canonical(payload))] = EvidenceContent(
                kind="source",
                title="lookup_result 授权源码片段",
                description="按原文件摘要重新核验的公开案例第107—110行；不是模型补丁。",
                source=ReadableSource.model_validate(
                    {key: source[key] for key in ("path", "start_line", "end_line", "text")}
                ),
            )
        except (ResourceError, ValueError, OSError, StopIteration):
            # Nothing from unverified files or an exception is returned to the caller.
            continue
    return result


def resolve_evidence(
    summary: AnalysisSummary, summary_sha256: str, *, root: Path | None = None
) -> EvidenceResponse:
    # Public fixture reconstruction is never used for imported/private evidence.
    candidates = (
        _public_content(summary.task_id, root) if summary.source_kind == "synthetic" else {}
    )
    unavailable = EvidenceContent(
        kind="unavailable", title="证据内容不可用", description=UNAVAILABLE
    )
    items = []
    for ref in summary.evidence_refs:
        content = candidates.get(ref.sha256, unavailable)
        try:
            items.append(EvidenceItem(ref=ref, **content.model_dump()))
        except ValidationError:
            items.append(EvidenceItem(ref=ref, **unavailable.model_dump()))
    return EvidenceResponse(
        task_id=summary.task_id, summary_sha256=summary_sha256, evidence=tuple(items)
    )
