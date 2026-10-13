"""P0-02: a bounded, single-call SDK adapter for reviewed local profiles."""

import math
import os
import sys
import time
from collections.abc import Awaitable, Callable
from importlib.metadata import version
from typing import TextIO, TypeVar
from uuid import uuid4

import anyio
from mcp import ClientSession, MCPError, StdioServerParameters, types
from mcp.client.stdio import DEFAULT_INHERITED_ENV_VARS, stdio_client
from mcp_types import CONNECTION_CLOSED, REQUEST_TIMEOUT
from pydantic import ValidationError

from agent_workbench.checker import (
    MAX_BYTES,
    InputLimitError,
    UnsupportedNumberError,
    parse_json_bytes,
)
from agent_workbench.cli import run_check
from agent_workbench.mcp_config import (
    PUBLIC_ARCHIVE_SHA256,
    PUBLIC_COMMIT,
    CallCase,
    PublicVerification,
    ServerConfig,
    canonical,
    digest,
    resolve_launch,
)
from agent_workbench.mcp_models import ContentSummary, MCPReport, Outcome
from agent_workbench.models import Finding, Report, incomplete

T = TypeVar("T")


class EvidenceSession(ClientSession):
    async def validate_tool_result(self, name: str, result: types.CallToolResult) -> None:
        """Transfer ONLY output-schema validation to our bounded checker.

        Protocol decoding/correlation remains in the official SDK. Every result
        returned through this hook must go through run_check before a pass.
        """


class _Stop(Exception):
    def __init__(self, code: str, outcome: Outcome = "unsupported") -> None:
        self.code = code
        self.outcome = outcome


def _leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for item in error.exceptions for leaf in _leaves(item)]
    return [error]


class _Run:
    def __init__(self, stage_timeout: float, total_timeout: float) -> None:
        self.started = time.monotonic()
        self.deadline = self.started + total_timeout
        self.stage_timeout = stage_timeout
        self.sent = False
        self.received = False
        self.report = MCPReport(invocation_id=str(uuid4()))

    def budget(self) -> float:
        remaining = min(self.stage_timeout, self.deadline - time.monotonic())
        if remaining < 0.1:
            raise _Stop("check_budget_exhausted")
        return remaining

    async def phase(self, action: Callable[[], Awaitable[T]]) -> T:
        with anyio.fail_after(self.budget()):
            return await action()

    async def check(self, envelope: dict[str, object]) -> Report:
        raw = canonical(envelope)
        # run_check owns a killable process; thread waits are not abandoned.
        return await anyio.to_thread.run_sync(run_check, raw, self.budget())

    async def session(self, session: EvidenceSession, case: CallCase) -> None:
        initialized = await self.phase(session.initialize)
        if initialized.protocol_version != "2025-11-25":
            raise _Stop("unsupported_protocol")
        self.report.source.protocol_version = "2025-11-25"
        if initialized.capabilities.tools is None:
            raise _Stop("tools_capability_missing")

        tools: dict[str, types.Tool] = {}
        seen_cursors: set[str] = set()
        cursor: str | None = None
        with anyio.fail_after(self.budget()):
            for _ in range(10):
                page = await session.list_tools(
                    params=types.PaginatedRequestParams(cursor=cursor)
                    if cursor is not None
                    else None
                )
                for tool in page.tools:
                    if tool.name in tools:
                        raise _Stop("duplicate_tool_name")
                    tools[tool.name] = tool
                    if len(tools) > 100:
                        raise _Stop("tool_limit_exceeded")
                if page.next_cursor is None:
                    break
                if page.next_cursor in seen_cursors:
                    raise _Stop("pagination_cycle")
                seen_cursors.add(page.next_cursor)
                cursor = page.next_cursor
            else:
                raise _Stop("page_limit_exceeded")
        target = tools.get(case.tool)
        if target is None:
            raise _Stop("tool_not_found", "precheck_rejected")
        tool_doc: dict[str, object] = {"name": target.name, "input_schema": target.input_schema}
        if target.output_schema is not None:
            tool_doc["output_schema"] = target.output_schema
        self.report.source.tool_schema_sha256 = digest(canonical(tool_doc))
        envelope: dict[str, object] = {
            "schema_version": 1,
            "tool": tool_doc,
            "call": {
                "call_id": self.report.invocation_id,
                "tool_name": case.tool,
                "arguments": case.arguments,
            },
        }
        preflight = await self.check(envelope)
        # Missing output is expected before execution, not a failed tool call.
        findings = [f for f in preflight.findings if f.code != "result_missing"]
        if findings or preflight.checks.input != "passed":
            self.report.preflight_findings = findings or [
                Finding(code="preflight_incomplete", phase="adapter")
            ]
            self.report.adapter_outcome = (
                "precheck_rejected" if preflight.checks.input == "failed" else "unsupported"
            )
            return

        await anyio.lowlevel.checkpoint()
        budget = self.budget()
        self.sent = True
        with anyio.fail_after(budget):
            result = await session.call_tool(case.tool, case.arguments)
        self.received = True
        if not isinstance(result, types.CallToolResult):
            raise _Stop("unsupported_result")
        self.report.adapter_outcome = "tool_error" if result.is_error else "completed"
        if (
            len(canonical(result.model_dump(mode="python", by_alias=True, exclude_unset=True)))
            > MAX_BYTES
        ):
            raise _Stop("input_limit_exceeded")
        summaries: dict[str, ContentSummary] = {}
        for block in result.content:
            kind = (
                block.type
                if block.type in ("text", "image", "audio", "resource", "resource_link")
                else "other"
            )
            summary = summaries.setdefault(kind, ContentSummary.model_validate({"kind": kind}))
            summary.items += 1
            if isinstance(block, types.TextContent):
                summary.text_characters += len(block.text)
        self.report.content_summary = list(summaries.values())
        mapped: dict[str, object] = {
            "call_id": self.report.invocation_id,
            "is_error": result.is_error,
        }
        if "structured_content" in result.model_fields_set:
            mapped["structured_content"] = result.structured_content
        envelope["result"] = mapped
        self.report.adapter_outcome = "tool_error" if result.is_error else "completed"
        self.report.contract_report = await self.check(envelope)

    def failure(self, error: BaseException) -> None:
        leaves = _leaves(error)
        stop = next((e for e in leaves if isinstance(e, _Stop)), None)
        if stop is not None:
            code, outcome = stop.code, stop.outcome
        elif any(isinstance(e, TimeoutError) for e in leaves):
            exhausted = time.monotonic() >= self.deadline
            code = (
                "check_budget_exhausted"
                if exhausted
                else ("call_timeout" if self.sent and not self.received else "stage_timeout")
            )
            outcome = (
                "outcome_unknown"
                if self.sent and not self.received
                else ("unsupported" if exhausted else "transport_error")
            )
        else:
            rpc = next((e for e in leaves if isinstance(e, MCPError)), None)
            if self.sent and not self.received:
                if rpc is not None and rpc.code not in (CONNECTION_CLOSED, REQUEST_TIMEOUT):
                    code, outcome = "protocol_error", "protocol_error"
                else:
                    code, outcome = "call_interrupted", "outcome_unknown"
            else:
                code, outcome = "transport_unavailable", "transport_error"
        if self.received:
            # Receiving a result is an observed fact even when validation fails.
            self.report.contract_report = incomplete(code)
            if self.report.adapter_outcome not in ("completed", "tool_error"):
                self.report.adapter_outcome = "unsupported"
        else:
            self.report.adapter_outcome = outcome
            self.report.preflight_findings.append(Finding(code=code, phase="adapter"))


async def run_mcp(
    config_raw: bytes,
    case_raw: bytes,
    *,
    stage_timeout: float = 5.0,
    total_timeout: float = 20.0,
    errlog: TextIO | None = None,
) -> MCPReport:
    """One trusted local experiment; no retries, raw-value logs or arbitrary argv.

    Use AnyIO cancellation scopes (not native task.cancel) to preserve the SDK's
    bounded shutdown. Raw wire output limits and hard isolation are P0-03.
    errlog is solely a test instrumentation seam; the CLI always discards it.
    """
    run = _Run(stage_timeout, total_timeout)
    if not (
        math.isfinite(stage_timeout)
        and 0.1 <= stage_timeout <= 5
        and math.isfinite(total_timeout)
        and 0.1 <= total_timeout <= 20
    ):
        run.failure(_Stop("invalid_budget"))
        return run.report
    run.report.source.sdk_version = version("mcp")
    if run.report.source.sdk_version != "2.3.0":
        run.failure(_Stop("unsupported_sdk_version"))
        return run.report
    try:
        config = ServerConfig.model_validate(parse_json_bytes(config_raw))
        case = CallCase.model_validate(parse_json_bytes(case_raw))
        launch = resolve_launch(config)
        run.report.source.profile = config.profile
        run.report.source.config_sha256 = digest(canonical(config.model_dump()))
        run.report.source.case_sha256 = digest(canonical(case.model_dump()))
        run.report.source.server_code_sha256 = digest(launch.script.read_bytes())
        run.report.source.server_dependencies_sha256 = digest(launch.dependencies.read_bytes())
    except (ValidationError, ValueError, OSError, RecursionError) as error:
        code = "invalid_config_or_case"
        outcome: Outcome = "precheck_rejected"
        if isinstance(error, (InputLimitError, UnsupportedNumberError)):
            code, outcome = "unsupported_input", "unsupported"
        run.report.adapter_outcome = outcome
        run.report.preflight_findings = [Finding(code=code, phase="config")]
        return run.report
    # Explicit overrides defeat SDK defaults: never inherit the user's HOME,
    # shell variables or personal executable search path.
    environment = dict.fromkeys(DEFAULT_INHERITED_ENV_VARS, "")
    environment.update(HOME=str(launch.cwd), PATH="/usr/bin:/bin", LANG="C.UTF-8")
    params = StdioServerParameters(
        command=str(launch.command), args=list(launch.args), cwd=launch.cwd, env=environment
    )
    try:
        with open(os.devnull, "w") as sink:
            with anyio.fail_after(max(0.001, run.deadline - time.monotonic())):
                if config.profile == "public-sdk-3644":
                    with anyio.fail_after(run.budget()):
                        verification = await anyio.run_process(
                            [
                                sys.executable,
                                "-I",
                                "-B",
                                str(launch.cwd / "prepare.py"),
                                "--verify-only",
                            ],
                            cwd=launch.cwd,
                            env=environment,
                            stderr=sink,
                            check=False,
                        )
                    if verification.returncode != 0:
                        raise _Stop("public_source_unverified")
                    try:
                        verified = PublicVerification.model_validate(
                            parse_json_bytes(verification.stdout)
                        )
                    except (ValueError, RecursionError):
                        raise _Stop("public_source_unverified") from None
                    if (
                        verified.commit != PUBLIC_COMMIT
                        or verified.archive_sha256 != PUBLIC_ARCHIVE_SHA256
                        or verified.lock_sha256 != run.report.source.server_dependencies_sha256
                    ):
                        raise _Stop("public_source_unverified")
                    run.report.source.server_revision = verified.commit
                    run.report.source.source_tree_sha256 = verified.source_tree_sha256
                async with stdio_client(params, errlog=errlog or sink) as (read, write):
                    async with EvidenceSession(read, write) as session:
                        await run.session(session, case)
    except Exception as error:
        run.failure(error)
    except anyio.get_cancelled_exc_class():
        run.failure(_Stop("run_cancelled", "outcome_unknown" if run.sent else "transport_error"))
    finally:
        run.report.elapsed_ms = round((time.monotonic() - run.started) * 1000)
    return run.report
