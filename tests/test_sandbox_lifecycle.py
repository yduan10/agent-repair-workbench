"""Negative lifecycle gates that must not require damaging the real Docker daemon."""

from contextlib import asynccontextmanager

import anyio
import pytest

from agent_workbench.mcp_config import canonical
from agent_workbench.models import Report
from agent_workbench.runner import service
from agent_workbench.runner.docker import DockerFailure
from agent_workbench.runner.models import ImageManifest

CASE = canonical({"case_id": "lifecycle", "tool": "lookup", "arguments": {"id": 1}})


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake(monkeypatch):
    class Control:
        env = {}
        created = False
        cleaned = 0
        verify_error = False
        create_error = False
        cleanup_ok = True
        daemon_dead = False
        cancel_on_create = None

        @classmethod
        async def connect(cls):
            return cls()

        async def create(self, *args):
            Control.created = True
            if Control.cancel_on_create:
                Control.cancel_on_create.cancel()
            if Control.create_error:
                raise DockerFailure("create_unconfirmed")
            return "a" * 64

        async def verify(self, *args):
            await anyio.lowlevel.checkpoint()
            if Control.verify_error:
                raise DockerFailure("container_policy_mismatch")

        async def inspect(self, *args):
            if Control.daemon_dead:
                raise DockerFailure("docker_timeout")
            return {"State": {"Running": True, "OOMKilled": False, "ExitCode": 0}}

        async def cleanup(self, *args):
            Control.cleaned += 1
            return Control.cleanup_ok

        def attach_args(self, *args):
            return []

    class Process:
        async def wait(self):
            return 0

    async def open_process(*args, **kwargs):
        return Process()

    @asynccontextmanager
    async def transport(*args):
        yield None, None

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    async def successful(run, *args):
        run.sent = run.received = True
        run.report.adapter_outcome = "completed"
        run.report.contract_report = Report(status="passed")

    async def close(*args):
        pass

    manifest = ImageManifest(
        image_id="sha256:" + "a" * 64,
        source_sha256="b" * 64,
        base_digest="python@sha256:"
        "a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134",
    )
    monkeypatch.setattr(service, "DockerControl", Control)
    monkeypatch.setattr(service, "verified_image", lambda: manifest)
    monkeypatch.setattr(service.anyio, "open_process", open_process)
    monkeypatch.setattr(service, "bounded_transport", transport)
    monkeypatch.setattr(service, "EvidenceSession", Session)
    monkeypatch.setattr(service._Run, "session", successful)
    monkeypatch.setattr(service, "_close_attach", close)
    return Control


@pytest.mark.anyio
async def test_valid_result_with_failed_cleanup_never_passes(fake):
    fake.cleanup_ok = False
    report = await service.run_sandbox(b"{}", CASE)
    assert report.exit_code() == 2
    assert report.mcp.adapter_outcome == "completed"
    assert report.mcp.contract_report.status == "inconclusive"
    assert report.execution.cleanup == "unconfirmed"
    assert fake.cleaned == 1


@pytest.mark.anyio
async def test_daemon_death_never_claims_absence(fake):
    fake.daemon_dead = True
    report = await service.run_sandbox(b"{}", CASE)
    assert report.exit_code() == 2
    assert report.execution.cleanup == "unconfirmed"


@pytest.mark.anyio
async def test_ambiguous_create_not_cleared_by_instant_absence(fake):
    fake.create_error = True
    report = await service.run_sandbox(b"{}", CASE)
    assert report.exit_code() == 2
    assert report.execution.cleanup == "unconfirmed"
    assert fake.cleaned == 1


@pytest.mark.anyio
async def test_cancel_after_ack_before_start_cleans_exact_target(fake):
    with anyio.CancelScope() as scope:
        fake.cancel_on_create = scope
        report = await service.run_sandbox(b"{}", CASE)
    assert report.execution.cleanup == "removed"
    assert report.exit_code() == 2
    assert fake.cleaned == 1


@pytest.mark.anyio
async def test_policy_rejected_before_execution(fake):
    fake.verify_error = True
    report = await service.run_sandbox(b"{}", CASE)
    assert report.execution.error == "container_policy_mismatch"
    assert report.execution.cleanup == "removed"
    assert report.mcp.source.protocol_version is None


@pytest.mark.anyio
@pytest.mark.parametrize("value", [b'{"command":"SECRET"}', b'{"scenario":"BAD"}', b"null"])
async def test_bad_configuration_has_no_execution(fake, value):
    report = await service.run_sandbox(value, CASE)
    assert report.mcp.adapter_outcome == "precheck_rejected"
    assert not fake.created and fake.cleaned == 0
    assert "SECRET" not in report.model_dump_json()


@pytest.mark.parametrize("tamper", ["source", "image", "base", "extra", "symlink"])
def test_image_manifest_and_source_tamper_rejected(tmp_path, tamper):
    from agent_workbench.mcp_config import digest

    source = tmp_path / "containers/p0_03"
    source.mkdir(parents=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    names = ("Dockerfile", "server.py", "prepare.py")
    for name in names:
        (source / name).write_bytes(name.encode())
    manifest = {
        "image_id": "sha256:" + "a" * 64,
        "source_sha256": digest(b"\0".join(n.encode() + b"\0" + n.encode() for n in names)),
        "base_digest": "python@sha256:"
        "a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134",
    }
    path = artifacts / "p0-03-image.json"
    path.write_bytes(canonical(manifest))
    assert service.verified_image(tmp_path).image_id == manifest["image_id"]
    if tamper == "source":
        (source / "server.py").write_text("changed")
    elif tamper == "symlink":
        (source / "server.py").unlink()
        (source / "server.py").symlink_to(source / "prepare.py")
    else:
        manifest[{"image": "image_id", "base": "base_digest", "extra": "command"}[tamper]] = "bad"
        path.write_bytes(canonical(manifest))
    with pytest.raises((ValueError, OSError)):
        service.verified_image(tmp_path)
