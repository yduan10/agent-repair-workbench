"""P0-05b actual checker/source/Docker tools, with host-only authorization and admission."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import anyio
from pydantic import JsonValue, TypeAdapter

from agent_workbench.analysis_store.fencing import AnalysisFence
from agent_workbench.analysis_store.models import AnalysisEvent, ExecutionReservation
from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.cli import run_check
from agent_workbench.controlled_tools.contracts import (
    CheckContract,
    ReadContract,
    ReadEvidence,
    ReadSource,
    Reproduce,
    ToolDecision,
    ToolRequest,
    target_key,
)
from agent_workbench.controlled_tools.resources import TaskResourceRegistry, read_verified
from agent_workbench.controlled_tools.responses import ErrorCode, ResourceError, ToolResponse
from agent_workbench.mcp_config import ROOT, canonical, digest
from agent_workbench.orchestration.codec import decode
from agent_workbench.orchestration.contracts import AnalysisSummary, EvidenceRef, Role, TaskSpec
from agent_workbench.orchestration.policy import AuthorizationContext, PolicyError, authorize
from agent_workbench.run_store.execution import terminal_status
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.models import SandboxConfig
from agent_workbench.runner.service import run_sandbox


@dataclass(frozen=True)
class ExecutionContext:
    """Private candidate tool reservation; reserve_execution commits this atomically."""

    summary: AnalysisSummary
    expected_revision: int
    expected_sha256: str
    fence: AnalysisFence
    event: AnalysisEvent


@dataclass(frozen=True)
class ToolExecution:
    response: ToolResponse
    task: TaskSpec
    grants: AuthorizationContext
    summary: AnalysisSummary | None = None
    summary_sha256: str | None = None
    cancelled: bool = False


async def _owned[T](
    operation: Coroutine[object, object, T], *, cancel_operation: bool
) -> tuple[T, bool]:
    """Native parent cancellation cannot abandon owned work or interrupt its cleanup.

    Docker receives cancellation through its AnyIO scope, where its cleanup shield is
    effective. A checker thread is not cancelled: its bounded subprocess must be joined.
    """
    interrupted = False
    scope: anyio.CancelScope | None = None

    async def worker() -> T:
        nonlocal scope
        with anyio.CancelScope() as owner:
            scope = owner
            if interrupted and cancel_operation:
                owner.cancel()
            return await operation
        raise asyncio.CancelledError

    task = asyncio.create_task(worker())
    while True:
        try:
            if interrupted:
                with anyio.CancelScope(shield=True):
                    value = await asyncio.shield(task)
            else:
                value = await asyncio.shield(task)
            return value, interrupted
        except asyncio.CancelledError:
            interrupted = True
            if task.done():
                return task.result(), True
            if cancel_operation and scope is not None:
                scope.cancel()


class ToolRuntime:
    def __init__(
        self,
        registry: TaskResourceRegistry,
        *,
        store: AnalysisStore | None = None,
        image_root: Path | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.image_root = image_root if image_root is not None else ROOT

    def _result(
        self,
        request: ToolRequest,
        *,
        payload: dict[str, JsonValue] | None = None,
        refs: tuple[EvidenceRef, ...] = (),
        versions: tuple[str, ...] = (),
        error: ErrorCode | None = None,
        reservation: ExecutionReservation | None = None,
        cancelled: bool = False,
    ) -> ToolExecution:
        response = ToolResponse(
            request_id=request.request_id,
            tool=request.tool,
            status=(
                "ok"
                if error is None
                else "outcome_unknown"
                if error == "RESULT_UNKNOWN"
                else "failed"
                if error == "TOOL_FAILURE"
                else "rejected"
            ),
            error_code=error,
            evidence_refs=refs,
            observed_versions=versions,
            payload=payload or {},
        )
        return ToolExecution(
            response=response,
            task=self.registry.task_spec(),
            grants=self.registry.authorization(),
            summary=reservation.summary if reservation else None,
            summary_sha256=reservation.summary_sha256 if reservation else None,
            cancelled=cancelled,
        )

    async def execute(
        self,
        role: Role,
        request: ToolRequest,
        *,
        timeout_seconds: float,
        reservation: ExecutionContext | None = None,
    ) -> ToolExecution:
        """Caller reserves tool budget first (T05 reserves its candidate in the DB transaction).

        timeout_seconds is the execution allowance, not the cleanup allowance. The coordinator
        separately reserves 15 seconds for Docker cleanup and bounded persistence.
        """
        try:
            if role not in ("diagnosis", "repair", "verification"):
                raise ValueError("invalid_role")
            request = decode(
                canonical(
                    {
                        "schema_version": 1,
                        "action": "request_tool",
                        "request": request.model_dump(mode="json"),
                    }
                ),
                TypeAdapter(ToolDecision),
            ).request
        except (ValueError, AttributeError, TypeError):
            raise ResourceError("INVALID_INPUT") from None
        try:
            if not math.isfinite(timeout_seconds) or not 0.1 <= timeout_seconds <= 30:
                raise ResourceError("BUDGET_EXCEEDED")
            authorize(
                self.registry.task_spec(),
                role,
                ToolDecision(action="request_tool", request=request),
                self.registry.authorization(),
            )
            if not isinstance(request, ReadEvidence):
                self.registry.ensure_capacity()
            if isinstance(request, Reproduce):
                return await self._reproduce(role, request, timeout_seconds, reservation)
            if isinstance(request, ReadEvidence):
                return self._result(
                    request,
                    payload=self.registry.evidence(request.evidence_ref, request.section),
                    refs=(request.evidence_ref,),
                )
            if isinstance(request, ReadContract):
                payload = self.registry.contract()
                ref = self.registry.register(
                    {
                        "summary": {"tool": "lookup", "contract_revision": request.revision},
                        "findings": [],
                        "events": [],
                    }
                )
                return self._result(
                    request, payload=payload, refs=(ref,), versions=(request.revision,)
                )
            if isinstance(request, ReadSource):
                payload = self.registry.source(request)
                # Source text is intentionally absent from registry/persistent evidence.
                ref = self.registry.register(
                    {
                        "summary": {key: value for key, value in payload.items() if key != "text"},
                        "findings": [],
                        "events": [],
                    }
                )
                return self._result(
                    request,
                    payload=payload,
                    refs=(ref,),
                    versions=(request.snapshot_id, self.registry.source_sha256()),
                )
            assert isinstance(request, CheckContract)
            raw = self.registry.verify_case()
            # Do not abandon a thread that owns a spawned checker. The checker kills/joins it.
            report, interrupted = await _owned(
                anyio.to_thread.run_sync(run_check, raw, timeout_seconds), cancel_operation=False
            )
            if interrupted:
                raise asyncio.CancelledError
            safe = report.model_dump(mode="json")
            ref = self.registry.register(
                {
                    "summary": report.model_dump(mode="json", exclude={"findings"}),
                    "findings": safe["findings"],
                    "events": [],
                }
            )
            return self._result(
                request, payload=safe, refs=(ref,), versions=(request.contract_revision,)
            )
        except PolicyError:
            return self._result(request, error="PERMISSION_DENIED")
        except ResourceError as error:
            return self._result(request, error=error.code)
        except (OSError, ValueError, RuntimeError):
            return self._result(request, error="TOOL_FAILURE")

    async def _reproduce(
        self,
        role: Role,
        request: Reproduce,
        timeout_seconds: float,
        context: ExecutionContext | None,
    ) -> ToolExecution:
        if self.store is None or context is None:
            raise ResourceError("PERMISSION_DENIED")
        task = self.registry.task_spec()
        event = AnalysisEvent.model_validate_json(context.event.model_dump_json())
        summary = AnalysisSummary.model_validate_json(context.summary.model_dump_json())
        if (
            summary.task_id != task.task_id
            or summary.state.intent != task.intent
            or summary.budget != task.budget
            or summary.source_kind != task.source_kind
            or not set(summary.evidence_refs) <= set(task.evidence)
            or not set(event.evidence_refs) <= set(task.evidence)
            or event.role != role
            or event.kind != "tool_started"
            or event.tool != request.tool
            or event.call_id != request.request_id
            or event.request_sha256 != target_key(request)
        ):
            raise ResourceError("PERMISSION_DENIED")
        config_raw, case_raw = self.registry.reproduction()
        # The image's exact server must match the source supplied to these agents.
        read_verified(self.image_root, "containers/p0_03/server.py", self.registry.source_sha256())
        try:
            admitted = self.store.reserve_execution(
                task_id=task.task_id,
                request_id=request.request_id,
                payload_sha256=target_key(request),
                config=SandboxConfig.model_validate_json(config_raw),
                case_sha256=digest(case_raw),
                summary=summary,
                expected_revision=context.expected_revision,
                expected_sha256=context.expected_sha256,
                fence=context.fence,
                event=event,
            )
        except StoreError as error:
            return self._result(
                request,
                error=(
                    "REQUEST_CONFLICT"
                    if error.code == "execution_link_conflict"
                    else "STALE_VERSION"
                    if "conflict" in error.code
                    else "TOOL_FAILURE"
                ),
            )
        interrupted = False
        if admitted.created:
            claim = admitted.claim
            assert claim is not None and claim.run.attempt_id is not None
            try:
                report, interrupted = await _owned(
                    run_sandbox(
                        config_raw,
                        case_raw,
                        stage_timeout=min(timeout_seconds, 5),
                        total_timeout=timeout_seconds,
                        run_id=claim.run.attempt_id,
                        image_root=self.image_root,
                    ),
                    cancel_operation=True,
                )
                report.record_id = admitted.run.run_id
                with anyio.CancelScope(shield=True):
                    runs = RunStore(self.store.directory)
                    try:
                        runs.finish(
                            report.record_id,
                            report.run_id,
                            claim.token,
                            expected_version=claim.run.version,
                            status=terminal_status(report),
                            report=report,
                            executor_state=(
                                "unavailable"
                                if report.execution.cleanup == "unconfirmed"
                                else "absent"
                            ),
                        )
                    finally:
                        runs.close()
            except (Exception, anyio.get_cancelled_exc_class()):
                # Admission is durable. Never retry after an interrupted/unsaved result.
                with anyio.CancelScope(shield=True):
                    return self._unknown(request, admitted)
        with anyio.CancelScope(shield=True):
            try:
                report = self.store.read_report(task.task_id, admitted.run.run_id)
                # read_report validates task binding, canonical bytes, hash and both IDs.
                report_sha = digest(canonical(report.model_dump(mode="json")))
                findings = (
                    report.mcp.contract_report.model_dump(mode="json")["findings"]
                    if report.mcp.contract_report
                    else []
                )
                payload: dict[str, JsonValue] = {
                    "execution_record_id": admitted.run.run_id,
                    "attempt_id": report.run_id,
                    "report_sha256": report_sha,
                    "status": terminal_status(report),
                    "adapter_outcome": report.mcp.adapter_outcome,
                    "contract_status": (
                        report.mcp.contract_report.status if report.mcp.contract_report else None
                    ),
                    "cleanup": report.execution.cleanup,
                    "elapsed_ms": report.mcp.elapsed_ms,
                    "source_sha256": report.execution.source_sha256,
                    "findings": findings,
                }
                ref = self.registry.register(
                    {
                        "summary": {
                            key: value for key, value in payload.items() if key != "findings"
                        },
                        "findings": findings,
                        "events": [],
                    }
                )
                outcome_error = (
                    "RESULT_UNKNOWN" if terminal_status(report) == "outcome_unknown" else None
                )
                return self._result(
                    request,
                    payload=payload,
                    refs=(ref,),
                    versions=(request.profile_revision, report_sha),
                    error=cast(ErrorCode | None, outcome_error),
                    reservation=admitted,
                    cancelled=interrupted,
                )
            except (StoreError, ValueError, ResourceError):
                return self._unknown(request, admitted)

        return self._unknown(request, admitted)

    def _unknown(self, request: Reproduce, admitted: ExecutionReservation) -> ToolExecution:
        return self._result(
            request,
            payload={
                "execution_record_id": admitted.run.run_id,
                "attempt_id": admitted.run.attempt_id,
            },
            error="RESULT_UNKNOWN",
            reservation=admitted,
        )
