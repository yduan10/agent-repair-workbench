"""One isolated MCP invocation. No retries, arbitrary commands or implicit image builds."""

import math
import time
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import anyio
from anyio.abc import Process

from agent_workbench.checker import parse_json_bytes
from agent_workbench.cli import _read
from agent_workbench.mcp_adapter import EvidenceSession, _Run, _Stop
from agent_workbench.mcp_config import ROOT, CallCase, canonical, digest
from agent_workbench.runner.docker import DockerControl, DockerFailure
from agent_workbench.runner.models import ImageManifest, SandboxConfig, SandboxReport
from agent_workbench.runner.transport import WireState, bounded_transport


def verified_image(root: Path = ROOT) -> ImageManifest:
    manifest = ImageManifest.model_validate(
        parse_json_bytes(_read(root / "artifacts/p0-03-image.json"))
    )
    parts = []
    for name in ("Dockerfile", "server.py", "prepare.py"):
        parts.append(name.encode() + b"\0" + _read(root / "containers/p0_03" / name))
    if digest(b"\0".join(parts)) != manifest.source_sha256:
        raise ValueError("source_changed")
    return manifest


async def _close_attach(process: Process) -> None:
    if process.returncode is None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    with anyio.move_on_after(0.5):
        await process.wait()
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    with anyio.fail_after(1):
        await process.wait()
        await process.aclose()


async def run_sandbox(
    config_raw: bytes,
    case_raw: bytes,
    *,
    stage_timeout: float = 5,
    total_timeout: float = 30,
    run_id: str | None = None,
) -> SandboxReport:
    run = _Run(stage_timeout, total_timeout)
    report = SandboxReport(run_id=run_id or str(uuid4()), mcp=run.report)
    execution = report.execution
    state = WireState()
    control: DockerControl | None = None
    process: Process | None = None
    create_started = False
    create_ambiguous = False
    cleanup_attempted = False
    try:
        if not (
            math.isfinite(stage_timeout)
            and 0.1 <= stage_timeout <= 5
            and math.isfinite(total_timeout)
            and 0.1 <= total_timeout <= 30
        ):
            raise ValueError("invalid_budget")
        config = SandboxConfig.model_validate(parse_json_bytes(config_raw))
        case = CallCase.model_validate(parse_json_bytes(case_raw))
        manifest = verified_image()
        if version("mcp") != "2.3.0":
            raise ValueError("unsupported_sdk")
        execution.image_id = manifest.image_id
        execution.source_sha256 = manifest.source_sha256
        execution.scenario, execution.seed = config.scenario, config.seed
        run.report.source.profile = "isolated-fixture"
        run.report.source.config_sha256 = digest(canonical(config.model_dump()))
        run.report.source.case_sha256 = digest(canonical(case.model_dump()))
        run.report.source.source_tree_sha256 = manifest.source_sha256
    except (ValueError, OSError, RecursionError):
        run.failure(_Stop("sandbox_precheck_rejected", "precheck_rejected"))
        return report

    async def cleanup() -> None:
        nonlocal cleanup_attempted
        if not create_started or control is None or cleanup_attempted:
            return
        cleanup_attempted = True
        execution.cleanup = "unconfirmed"
        try:
            with anyio.fail_after(10):
                inspected = await control.inspect("awb-p003-" + report.run_id)
                if inspected is not None:
                    status = inspected["State"]
                    execution.oom_killed = bool(status["OOMKilled"])
                    if not status["Running"]:
                        execution.container_exit_code = int(status["ExitCode"])
                removed = await control.cleanup(report.run_id)
            if removed and not create_ambiguous:
                execution.cleanup = "removed"
        except (DockerFailure, TimeoutError, OSError):
            pass
        if execution.cleanup == "unconfirmed":
            execution.error = execution.error or "cleanup_unconfirmed"

    try:
        with anyio.fail_after(total_timeout):
            control = await DockerControl.connect()
            await anyio.lowlevel.checkpoint()
            create_started = True
            try:
                container = await control.create(
                    report.run_id, manifest.image_id, config.scenario, config.seed, config.lifetime
                )
            except DockerFailure as error:
                create_ambiguous = error.code == "create_unconfirmed"
                raise
            await control.verify(container, manifest.image_id)
            process = await anyio.open_process(control.attach_args(container), env=control.env)
            async with bounded_transport(process, state) as (read, write):
                try:
                    async with EvidenceSession(read, write) as session:
                        await run.session(session, case)
                    # Drain immediately trailing frames, including duplicated successful results.
                    await anyio.sleep(0.15)
                    inspected = await control.inspect(container)
                    if inspected is None:
                        raise DockerFailure("container_disappeared")
                    status = inspected["State"]
                    execution.oom_killed = bool(status["OOMKilled"])
                    if not status["Running"]:
                        execution.container_exit_code = int(status["ExitCode"])
                        if execution.container_exit_code or execution.oom_killed:
                            raise DockerFailure("container_failed")
                finally:
                    # Keep readers alive during rm to observe buffered bytes; do not close stdin
                    # first (it could turn an unobserved failed execution into a clean EOF).
                    with anyio.CancelScope(shield=True):
                        await cleanup()
                        with anyio.move_on_after(0.2):
                            await process.wait()
                            await anyio.sleep(0.02)
    except DockerFailure as error:
        execution.error = execution.error or error.code
        run.failure(_Stop(error.code, "outcome_unknown" if run.sent else "transport_error"))
    except Exception as error:
        run.failure(error)
    except anyio.get_cancelled_exc_class():
        run.failure(_Stop("run_cancelled", "outcome_unknown" if run.sent else "transport_error"))
    finally:
        with anyio.CancelScope(shield=True):
            if execution.cleanup != "removed":
                await cleanup()
            if process is not None:
                try:
                    await _close_attach(process)
                except (TimeoutError, OSError):
                    execution.error = execution.error or "attach_cleanup_unconfirmed"
        execution.stdout_bytes, execution.stderr_bytes = state.stdout_bytes, state.stderr_bytes
        execution.frames = state.frames
        execution.error = execution.error or state.error
        if execution.error:
            run.failure(
                _Stop(
                    execution.error,
                    "outcome_unknown" if run.sent and not run.received else "transport_error",
                )
            )
        run.report.elapsed_ms = round((time.monotonic() - run.started) * 1000)
    return report
