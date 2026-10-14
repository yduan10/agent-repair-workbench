"""Persist the right to execute before crossing the Docker boundary; never retry."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from agent_workbench.analysis_store.fencing import AnalysisFence
from agent_workbench.checker import parse_json_bytes
from agent_workbench.mcp_config import CallCase, canonical, digest
from agent_workbench.mcp_models import MCPReport
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import RunStatus, RunView, StoreError
from agent_workbench.run_store.schema import analysis_execution_links
from agent_workbench.run_store.store import RunStore
from agent_workbench.runner.docker import DockerControl, DockerFailure
from agent_workbench.runner.models import SandboxConfig, SandboxReport
from agent_workbench.runner.service import run_sandbox
from agent_workbench.web_runs.fencing import OwnerFence
from agent_workbench.web_runs.store import WebRunStore


def terminal_status(report: SandboxReport) -> RunStatus:
    """Unknown transport/cleanup evidence always takes precedence over apparent success."""
    execution, mcp = report.execution, report.mcp
    if execution.cleanup == "unconfirmed" or execution.error:
        return "outcome_unknown"
    if mcp.adapter_outcome == "outcome_unknown":
        return "outcome_unknown"
    if mcp.adapter_outcome == "transport_error" and any(
        item.code == "run_cancelled" for item in mcp.preflight_findings
    ):
        return "cancelled"
    if mcp.adapter_outcome in ("precheck_rejected", "tool_error"):
        return "failed"
    if mcp.adapter_outcome == "completed" and mcp.contract_report:
        if mcp.contract_report.status == "passed":
            return "succeeded"
        if mcp.contract_report.status == "failed":
            return "failed"
    return "outcome_unknown"


def _unavailable(code: str) -> SandboxReport:
    report = SandboxReport(run_id=str(uuid4()), mcp=MCPReport(invocation_id=str(uuid4())))
    report.execution.error = code
    return report


async def execute_saved(
    config_raw: bytes,
    case_raw: bytes,
    *,
    directory: Path | None = None,
    lease_seconds: int = 120,
) -> SandboxReport:
    # Invalid inputs take the existing preflight-only path, without persisting raw input.
    try:
        config = SandboxConfig.model_validate(parse_json_bytes(config_raw))
        case = CallCase.model_validate(parse_json_bytes(case_raw))
    except (ValueError, RecursionError):
        return await run_sandbox(config_raw, case_raw)
    store = RunStore(directory if directory is not None else state_directory())
    try:
        try:
            store.initialize()
            run = store.create(
                profile=config.profile,
                scenario=config.scenario,
                config_sha256=digest(canonical(config.model_dump())),
                case_sha256=digest(canonical(case.model_dump())),
            )
            claim = store.claim(
                run.run_id, expected_version=run.version, lease_seconds=lease_seconds
            )
        except StoreError:
            return _unavailable("persistence_unavailable")
        # Claim's transaction has committed. A crash from this point leaves durable running
        # evidence; reconciliation cannot infer business success and cannot repeat this call.
        assert claim.run.attempt_id is not None
        report = await run_sandbox(config_raw, case_raw, run_id=claim.run.attempt_id)
        report.record_id = run.run_id
        try:
            store.finish(
                run.run_id,
                claim.run.attempt_id,
                claim.token,
                expected_version=claim.run.version,
                status=terminal_status(report),
                report=report,
                executor_state=(
                    "absent" if report.execution.cleanup != "unconfirmed" else "unavailable"
                ),
            )
        except StoreError:
            # stdout remains useful evidence, but callers must not mistake an unsaved run
            # for a durably completed one. Never retry a call because its report write failed.
            report.execution.error = "persistence_failed"
        return report
    finally:
        store.close()


async def reconcile_runs(store: RunStore) -> list[RunView]:
    pending = store.expired()
    if not pending:
        return []
    control: DockerControl | None = None
    try:
        control = await DockerControl.connect()
    except (DockerFailure, OSError, RuntimeError):
        pass
    updated = []
    for run in pending:
        web = WebRunStore(store.directory)
        fences: list[OwnerFence | AnalysisFence] = []
        try:
            if web.is_active(run.run_id):
                fences.append(OwnerFence(store.directory))
            with store._transaction() as connection:
                task_id = connection.execute(
                    select(analysis_execution_links.c.task_id).where(
                        analysis_execution_links.c.record_id == run.run_id
                    )
                ).scalar_one_or_none()
            if task_id is not None:
                fences.append(AnalysisFence(store.directory, task_id))
            try:
                for fence in fences:
                    fence.acquire()
            except StoreError as error:
                if error.code in ("runner_busy", "analysis_busy"):
                    continue
                raise
            resource = "unavailable"
            if control is not None and run.attempt_id is not None:
                try:
                    item = await control.inspect("awb-p003-" + run.attempt_id)
                    if item is None:
                        resource = "absent"
                    elif not control._matches(item, run.attempt_id):
                        resource = "mismatch"
                    else:
                        resource = "running" if item["State"]["Running"] else "stopped"
                except (DockerFailure, OSError, KeyError, TypeError, RuntimeError):
                    resource = "unavailable"
            try:
                updated.append(
                    store.reconcile(
                        run.run_id, expected_version=run.version, executor_state=resource
                    )
                )
            except StoreError as error:
                if error.code not in ("state_conflict", "version_conflict", "run_conflict"):
                    raise
        finally:
            for fence in reversed(fences):
                fence.close()
            web.close()
    return updated
