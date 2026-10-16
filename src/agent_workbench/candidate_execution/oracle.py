"""Trusted host assertions over one bounded MCP session. Candidate text is never authority."""

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from importlib.metadata import version
from pathlib import Path
from typing import Protocol, TypeVar

import anyio
from anyio.abc import Process
from mcp import MCPError, types

from agent_workbench.candidate_execution.docker import CandidateDockerControl, verified_image
from agent_workbench.candidate_execution.models import (
    STEPS,
    OracleReport,
    OracleStep,
    Scenario,
    StepCode,
    StepName,
)
from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.candidates.snapshots import SnapshotHandle, SnapshotStore
from agent_workbench.mcp_adapter import EvidenceSession, _leaves
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.runner.docker import DockerControl, DockerFailure
from agent_workbench.runner.service import _close_attach
from agent_workbench.runner.transport import WireState, bounded_transport

T = TypeVar("T")
INPUT_SCHEMA = {
    "type": "object",
    "properties": {"id": {"type": "integer"}},
    "required": ["id"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"count": {"type": "integer"}},
    "required": ["count"],
    "additionalProperties": False,
}
# Only this host-owned sequence is accepted; no model-supplied suite or expected values.
SEQUENCE: tuple[tuple[StepName, int | str, int | None], ...] = (
    ("valid_one", 1, 1),
    ("invalid_type", "bad", None),
    ("valid_zero", 0, 2),
    ("valid_negative", -1, 3),
)


def suite_sha256() -> str:
    return digest(
        canonical(
            {
                "version": 1,
                "sequence": SEQUENCE,
                "input": INPUT_SCHEMA,
                "output": OUTPUT_SCHEMA,
                "rules": [
                    "protocol_2025-11-25",
                    "single_lookup_no_cursor",
                    "schema_before_after",
                    "strict_integer_count",
                    "invalid_input_-32602_no_increment",
                    "alive_after",
                    "all_steps_required",
                    "snapshot_unchanged",
                    "cleanup_confirmed",
                ],
            }
        )
    )


# Explicit trusted dependency closure. Include import-time contract/policy modules,
# even where this oracle calls only one helper, because their module code runs in
# the host. Adding a trusted import requires updating this list and its gate.
# Container sources have a separate prepared-image hash; snapshots have their own
# file/tree hashes. The locked SDK/AnyIO/Pydantic dependency graph is bound here.
ORACLE_SAFETY_FILES = (
    "src/agent_workbench/repair_cases/__init__.py",
    "src/agent_workbench/repair_cases/profiles.py",
    "src/agent_workbench/repair_cases/bindings.py",
    "src/agent_workbench/__init__.py",
    "src/agent_workbench/candidate_execution/__init__.py",
    "src/agent_workbench/candidate_execution/models.py",
    "src/agent_workbench/candidate_execution/docker.py",
    "src/agent_workbench/candidate_execution/oracle.py",
    "src/agent_workbench/candidate_execution/compare.py",
    "src/agent_workbench/runner/__init__.py",
    "src/agent_workbench/runner/docker.py",
    "src/agent_workbench/runner/models.py",
    "src/agent_workbench/runner/service.py",
    "src/agent_workbench/runner/transport.py",
    "src/agent_workbench/candidates/__init__.py",
    "src/agent_workbench/candidates/contracts.py",
    "src/agent_workbench/candidates/snapshots.py",
    "src/agent_workbench/controlled_tools/__init__.py",
    "src/agent_workbench/controlled_tools/contracts.py",
    "src/agent_workbench/controlled_tools/resources.py",
    "src/agent_workbench/controlled_tools/responses.py",
    "src/agent_workbench/orchestration/__init__.py",
    "src/agent_workbench/orchestration/contracts.py",
    "src/agent_workbench/orchestration/policy.py",
    "src/agent_workbench/agents/__init__.py",
    "src/agent_workbench/agents/diagnosis/__init__.py",
    "src/agent_workbench/agents/diagnosis/contracts.py",
    "src/agent_workbench/agents/repair/__init__.py",
    "src/agent_workbench/agents/repair/contracts.py",
    "src/agent_workbench/agents/verification/__init__.py",
    "src/agent_workbench/agents/verification/contracts.py",
    "src/agent_workbench/checker.py",
    "src/agent_workbench/cli.py",
    "src/agent_workbench/mcp_adapter.py",
    "src/agent_workbench/mcp_config.py",
    "src/agent_workbench/mcp_models.py",
    "src/agent_workbench/models.py",
    "uv.lock",
)


def oracle_sha256() -> str:
    """Bind every audited host safety dependency and lockfile to this run's oracle."""
    root = Path(__file__).resolve().parents[3]
    return digest(
        b"\0".join(n.encode() + b"\0" + (root / n).read_bytes() for n in ORACLE_SAFETY_FILES)
    )


SUITE_SHA256 = suite_sha256()
ORACLE_SHA256 = oracle_sha256()


def verify_oracle() -> bool:
    try:
        return suite_sha256() == SUITE_SHA256 and oracle_sha256() == ORACLE_SHA256
    except OSError:
        return False


class Session(Protocol):
    async def initialize(self) -> types.InitializeResult: ...
    async def list_tools(self) -> types.ListToolsResult: ...
    async def call_tool(
        self, name: str, arguments: dict[str, int | str]
    ) -> types.CallToolResult: ...


class SequenceOracle:
    """Host assertions are separately unit-testable; all production results pass through here."""

    def __init__(self, report: OracleReport, stage_timeout: float) -> None:
        self.report, self.stage_timeout = report, stage_timeout

    def step(self, name: StepName) -> OracleStep:
        return next(s for s in self.report.steps if s.name == name)

    def record(self, name: StepName, code: StepCode) -> None:
        step = self.step(name)
        step.code = code
        step.status = "passed" if code == "ok" else "failed"

    async def phase(self, action: Callable[[], Awaitable[T]]) -> T:
        with anyio.fail_after(self.stage_timeout):
            return await action()

    async def schema(self, session: Session, name: StepName) -> None:
        listed = await self.phase(session.list_tools)
        ok = (
            listed.next_cursor is None
            and len(listed.tools) == 1
            and listed.tools[0].name == "lookup"
            and canonical(listed.tools[0].input_schema) == canonical(INPUT_SCHEMA)
            and canonical(listed.tools[0].output_schema) == canonical(OUTPUT_SCHEMA)
        )
        self.record(name, "ok" if ok else "schema_mismatch")

    async def run(self, session: Session) -> None:
        initialized = await self.phase(session.initialize)
        if initialized.protocol_version != "2025-11-25" or initialized.capabilities.tools is None:
            self.record("initialize", "protocol_mismatch")
            return
        self.record("initialize", "ok")
        await self.schema(session, "schema_before")
        for name, argument, expected in SEQUENCE:
            try:
                with anyio.fail_after(self.stage_timeout):
                    result = await session.call_tool("lookup", {"id": argument})
            except MCPError as error:
                self.record(
                    name, "ok" if expected is None and error.code == -32602 else "wrong_error_code"
                )
                continue
            step = self.step(name)
            step.result_sha256 = digest(canonical(result.model_dump(mode="json", by_alias=True)))
            code: StepCode
            if expected is None:
                code = "invalid_input_accepted"
            elif result.is_error:
                code = "tool_error"
            elif "structured_content" not in result.model_fields_set:
                code = "structured_missing"
            elif not isinstance(result.structured_content, dict) or set(
                result.structured_content
            ) != {"count"}:
                code = "result_shape"
            elif type(result.structured_content["count"]) is not int:
                code = "count_type"
            elif result.structured_content["count"] != expected:
                code = "count_value"
            else:
                code = "ok"
            self.record(name, code)
        await self.schema(session, "schema_after")


def finalize(report: OracleReport) -> None:
    """No number of successful checks can hide a missing step, changed file, or cleanup gap."""
    report.status = "inconclusive"
    if tuple(s.name for s in report.steps) != STEPS:
        return
    if report.error == "attach_cleanup_unconfirmed":
        report.status = "outcome_unknown"
    elif report.cleanup == "unconfirmed":
        report.status, report.error = "outcome_unknown", "cleanup_unconfirmed"
    elif report.error == "run_cancelled":
        report.status = "cancelled"
    elif report.error or not (report.snapshot_verified_before and report.snapshot_verified_after):
        report.status = "inconclusive"
    elif any(s.status == "not_run" for s in report.steps):
        report.status = "inconclusive"
    elif any(s.status == "failed" for s in report.steps):
        report.status = "failed"
    elif report.cleanup == "removed" and report.image_id and report.image_source_sha256:
        report.status = "passed"


async def _execute(
    snapshot: SnapshotHandle,
    report: OracleReport,
    image_root: Path,
    stage_timeout: float,
    total_timeout: float,
) -> OracleReport:
    started = time.monotonic()
    state = WireState()
    candidate: CandidateDockerControl | None = None
    process: Process | None = None
    oracle = SequenceOracle(report, stage_timeout)
    cleaned = False
    attach_failed = False

    async def cleanup() -> None:
        nonlocal cleaned
        if candidate is None or not candidate.started or cleaned:
            return
        cleaned = True
        report.cleanup = "unconfirmed"
        try:
            with anyio.fail_after(10):
                if await candidate.cleanup():
                    report.cleanup = "removed"
        except (DockerFailure, TimeoutError, OSError):
            pass

    try:
        if not (
            math.isfinite(stage_timeout)
            and 0.1 <= stage_timeout <= 5
            and math.isfinite(total_timeout)
            and 0.1 <= total_timeout <= 30
        ):
            report.error = "invalid_budget"
            return report
        if not verify_oracle():
            report.error = "oracle_unverified"
            return report
        if version("mcp") != "2.3.0":
            report.error = "unsupported_sdk"
            return report
        try:
            manifest = verified_image(image_root)
            report.image_id, report.image_source_sha256 = manifest.image_id, manifest.source_sha256
        except (ValueError, OSError, RecursionError):
            report.error = "image_unverified"
            return report
        SnapshotStore(snapshot.root.parent).verify(snapshot)
        report.snapshot_verified_before = True
        with anyio.fail_after(total_timeout):
            control = await DockerControl.connect()
            candidate = CandidateDockerControl(
                control, snapshot, manifest, report.scenario, report.attempt_id
            )
            cid = await candidate.create()
            await candidate.verify()
            process = await anyio.open_process(control.attach_args(cid), env=control.env)
            async with bounded_transport(process, state) as (read, write):
                try:
                    async with EvidenceSession(read, write) as session:
                        await oracle.run(session)
                        # Preserve the live session while checking process state and tail frames.
                        await anyio.sleep(0.15)
                        item = await candidate.inspect()
                        alive = (
                            item is not None
                            and isinstance(item.get("State"), dict)
                            and item["State"].get("Running") is True
                        )
                        oracle.record("alive", "ok" if alive else "process_exited")
                finally:
                    # Continue draining bounded pipes until exact-ID removal is acknowledged.
                    with anyio.CancelScope(shield=True):
                        await cleanup()
                        with anyio.move_on_after(0.2):
                            await process.wait()
                            await anyio.sleep(0.02)
    except CandidateError:
        report.error = "snapshot_unverified"
    except DockerFailure:
        report.error = "docker_failure"
    except TimeoutError:
        report.error = "deadline_exceeded"
    except anyio.get_cancelled_exc_class():
        report.error = "run_cancelled"
    except Exception as error:
        # No exception string, RPC message, path, stdout or stderr enters the report.
        report.error = (
            "deadline_exceeded"
            if any(isinstance(e, TimeoutError) for e in _leaves(error))
            else "protocol_error"
        )
    finally:
        with anyio.CancelScope(shield=True):
            await cleanup()
            if process is not None:
                try:
                    await _close_attach(process)
                except (TimeoutError, OSError):
                    attach_failed = True
        if report.snapshot_verified_before:
            try:
                SnapshotStore(snapshot.root.parent).verify(snapshot)
                report.snapshot_verified_after = True
            except (CandidateError, OSError):
                report.error = "snapshot_unverified"
        if report.image_id is not None:
            try:
                if verified_image(image_root) != manifest:
                    raise ValueError
            except (ValueError, OSError, RecursionError):
                report.error = "image_unverified"
        if state.error:
            report.error = "wire_error"
        if not verify_oracle():
            report.error = "oracle_unverified"
        report.stdout_bytes, report.stderr_bytes, report.frames = (
            state.stdout_bytes,
            state.stderr_bytes,
            state.frames,
        )
        report.elapsed_ms = round((time.monotonic() - started) * 1000)
        if attach_failed:
            report.error = "attach_cleanup_unconfirmed"
        finalize(report)
    return report


async def run_oracle(
    snapshot: SnapshotHandle,
    *,
    scenario: Scenario,
    attempt_id: str,
    image_root: Path,
    stage_timeout: float = 3,
    total_timeout: float = 25,
) -> OracleReport:
    """One pre-registered attempt only. Native repeated cancellation waits for cleanup.

    Caller owns persistence/idempotency and invokes separate attempts for pass/wrong_type.
    Host SIGKILL requires later persisted-ID reconciliation; no independent expiry promise.
    """
    report = OracleReport(
        attempt_id=attempt_id,
        snapshot_id=snapshot.ref.snapshot_id,
        snapshot_tree_sha256=snapshot.ref.tree_sha256,
        snapshot_file_sha256=snapshot.ref.file_sha256,
        suite_sha256=SUITE_SHA256,
        oracle_sha256=ORACLE_SHA256,
        scenario=scenario,
    )
    scope: anyio.CancelScope | None = None
    cancelled = False

    async def worker() -> OracleReport:
        nonlocal scope
        with anyio.CancelScope() as owner:
            scope = owner
            if cancelled:
                owner.cancel()
            return await _execute(snapshot, report, image_root, stage_timeout, total_timeout)
        if report.error != "attach_cleanup_unconfirmed":
            report.error = "run_cancelled"
        finalize(report)
        return report

    task = asyncio.create_task(worker())
    while True:
        try:
            with anyio.CancelScope(shield=cancelled):
                result = await asyncio.shield(task)
            if cancelled:
                if result.error != "attach_cleanup_unconfirmed":
                    result.error = "run_cancelled"
                finalize(result)
            return result
        except asyncio.CancelledError:
            cancelled = True
            if scope is not None:
                scope.cancel()
            if task.done():
                result = task.result()
                if result.error != "attach_cleanup_unconfirmed":
                    result.error = "run_cancelled"
                finalize(result)
                return result
