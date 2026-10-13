"""P0-03 control-plane unit tests; Docker operations are mocked."""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

import anyio
import pytest

from agent_workbench.runner import docker

RUN = "ed922172-ef4a-4d4e-b422-3c04982f32f4"
NAME = "awb-p003-" + RUN
CID = "c" * 64
IMAGE = "sha256:" + "a" * 64


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def control():
    return docker.DockerControl("/fixed/docker", "unix:///fixed/socket", {"PATH": "/usr/bin"})


def container() -> dict[str, Any]:
    return {
        "Id": CID,
        "Name": "/" + NAME,
        "Image": IMAGE,
        "Mounts": [],
        "State": {"Running": False, "Status": "created"},
        "Config": {
            "Image": IMAGE,
            "User": "65532:65532",
            "Entrypoint": docker.ENTRYPOINT,
            "Cmd": ["--scenario", "pass", "--seed", "0", "--lifetime", "45"],
            "OpenStdin": True,
            "Tty": False,
            "Volumes": None,
            "WorkingDir": "/tmp",
            "Labels": {docker.PROJECT_LABEL: docker.PROJECT, docker.RUN_LABEL: RUN},
            "Env": [
                "PATH=" + docker.ENV_RULES["PATH"],
                "LANG=C.UTF-8",
                "GPG_KEY=" + "A" * 40,
                "PYTHON_VERSION=3.12.13",
                "PYTHON_SHA256=" + "a" * 64,
            ],
        },
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "NanoCpus": 500_000_000,
            "Memory": 134_217_728,
            "MemorySwap": 134_217_728,
            "PidsLimit": 32,
            "Init": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Tmpfs": {"/tmp": docker.TMPFS},
            "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            "LogConfig": {"Type": "none", "Config": {}},
            "PidMode": "",
            "IpcMode": "private",
            "UTSMode": "",
            "UsernsMode": "",
        },
    }


@pytest.mark.anyio
async def test_connect_rejects_remote_and_omits_host_secret(monkeypatch):
    monkeypatch.setenv("AWB_TEST_SECRET", "sensitive")
    monkeypatch.setenv("DOCKER_HOST", "tcp://untrusted:2375")
    monkeypatch.setattr(docker.shutil, "which", lambda _: "/fixed/docker")

    async def execute(argv, env):
        assert "AWB_TEST_SECRET" not in env and "DOCKER_HOST" not in env
        return b"tcp://example:2375\n"

    monkeypatch.setattr(docker, "_execute", execute)
    with pytest.raises(docker.DockerFailure, match="docker_endpoint_rejected"):
        await docker.DockerControl.connect()


@pytest.mark.anyio
async def test_connect_local_pins_endpoint(monkeypatch):
    monkeypatch.setattr(docker.shutil, "which", lambda _: "/fixed/docker")
    monkeypatch.setattr(docker.Path, "is_socket", lambda _: True)

    async def execute(argv, env):
        return b"unix:///Users/test/.colima/default/docker.sock\n"

    monkeypatch.setattr(docker, "_execute", execute)
    result = await docker.DockerControl.connect()
    assert result.endpoint == "unix:///Users/test/.colima/default/docker.sock"
    assert result.attach_args(CID)[1:3] == ["--host", result.endpoint]


@pytest.mark.anyio
async def test_create_shields_ack_and_flags(control, monkeypatch):
    calls = []

    async def command(*args):
        scope.cancel()  # Cancellation arrives after the create request has started.
        await anyio.sleep(0)
        calls.append(args)
        return CID.encode()

    monkeypatch.setattr(control, "command", command)
    with anyio.CancelScope() as scope:
        assert await control.create(RUN, IMAGE, "pass", 0, 45) == CID
    args = calls[0]
    for flag, value in (
        ("--network", "none"),
        ("--pull", "never"),
        ("--memory", "128m"),
        ("--memory-swap", "128m"),
        ("--pids-limit", "32"),
        ("--log-driver", "none"),
        ("--user", "65532:65532"),
    ):
        assert args[args.index(flag) + 1] == value
    assert "--init" in args and "--read-only" in args
    assert "--volume" not in args and "--env" not in args
    assert control._created[CID][0] == RUN


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["timeout", "malformed_ack"])
async def test_create_uncertain_is_not_success(control, monkeypatch, mode):
    async def command(*args):
        if mode == "timeout":
            raise docker.DockerFailure("docker_timeout")
        return b"truncated id"

    monkeypatch.setattr(control, "command", command)
    with pytest.raises(docker.DockerFailure, match="create_unconfirmed"):
        await control.create(RUN, IMAGE, "pass", 0, 45)
    assert not control._created


@pytest.mark.anyio
@pytest.mark.parametrize("run,seed", [("../other", 0), (RUN, True), (RUN, 2**31)])
async def test_create_validates_before_command(control, monkeypatch, run, seed):
    async def command(*args):
        pytest.fail("invalid request reached daemon")

    monkeypatch.setattr(control, "command", command)
    with pytest.raises(docker.DockerFailure):
        await control.create(run, IMAGE, "pass", seed, 45)


@pytest.mark.anyio
async def test_inspect_absent_vs_daemon_error(control, monkeypatch):
    async def absent(*args):
        assert f"name=^/{NAME}$" in args
        return b""

    monkeypatch.setattr(control, "command", absent)
    assert await control.inspect(NAME) is None

    async def error(*args):
        raise docker.DockerFailure("docker_command_failed")

    monkeypatch.setattr(control, "command", error)
    with pytest.raises(docker.DockerFailure, match="docker_command_failed"):
        await control.inspect(NAME)


@pytest.mark.anyio
async def test_inspect_checks_identity(control, monkeypatch):
    state = container()
    state["Id"] = "d" * 64

    async def command(*args):
        return CID.encode() if args[1] == "ls" else json.dumps(state).encode()

    monkeypatch.setattr(control, "command", command)
    with pytest.raises(docker.DockerFailure, match="docker_inspect_invalid"):
        await control.inspect(NAME)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutation",
    ["none", "bind", "env", "entrypoint", "cpu", "labels", "image", "running", "tmpfs", "volume"],
)
async def test_actual_policy_verified(control, monkeypatch, mutation):
    state = copy.deepcopy(container())
    mutations = {
        "bind": (state["HostConfig"], "Binds", ["/home:/host"]),
        "env": (state["Config"], "Env", ["AWB_TEST_SECRET=hidden"]),
        "entrypoint": (state["Config"], "Entrypoint", ["sh"]),
        "cpu": (state["HostConfig"], "NanoCpus", 0),
        "labels": (state["Config"], "Labels", {}),
        "image": (state, "Image", "sha256:" + "b" * 64),
        "running": (state["State"], "Running", True),
        "tmpfs": (state["HostConfig"], "Tmpfs", {"/tmp": "rw,size=1g"}),
        "volume": (state, "Mounts", [{"Type": "volume", "Destination": "/host"}]),
    }
    if mutation != "none":
        mapping, key, value = mutations[mutation]
        mapping[key] = value
    control._created[CID] = (RUN, IMAGE, state["Config"]["Cmd"])

    async def inspect(name):
        return state

    monkeypatch.setattr(control, "inspect", inspect)
    if mutation == "none":
        await control.verify(CID, IMAGE)
    else:
        with pytest.raises(docker.DockerFailure, match="container_policy_mismatch"):
            await control.verify(CID, IMAGE)


@pytest.mark.anyio
@pytest.mark.parametrize("mismatch", [False, True])
async def test_cleanup_exact_match_and_confirmation(control, monkeypatch, mismatch):
    state = container()
    if mismatch:
        state["Config"]["Labels"][docker.RUN_LABEL] = "other"
    responses = iter([state, None])
    commands = []

    async def inspect(name):
        assert name == NAME
        return next(responses)

    async def command(*args):
        commands.append(args)
        return b""

    monkeypatch.setattr(control, "inspect", inspect)
    monkeypatch.setattr(control, "command", command)
    assert await control.cleanup(RUN) is (not mismatch)
    assert commands == ([] if mismatch else [("container", "rm", "--force", CID)])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,apply,expected",
    [
        ("running", True, "running"),
        ("exited", False, "stopped"),
        ("exited", True, "removed"),
        ("created", True, "unconfirmed"),
    ],
)
async def test_reap_never_force_removes_running(control, monkeypatch, status, apply, expected):
    state = container()
    state["State"] = {"Running": status == "running", "Status": status}
    responses = iter([state, None])
    commands = []

    async def inspect(name):
        return next(responses)

    async def command(*args):
        commands.append(args)
        return b""

    monkeypatch.setattr(control, "inspect", inspect)
    monkeypatch.setattr(control, "command", command)
    assert await control.reap(RUN, apply) == expected
    assert commands == ([("container", "rm", CID)] if expected == "removed" else [])


@pytest.mark.anyio
async def test_control_output_limit():
    stream = asyncio.StreamReader()
    stream.feed_data(b"secret" * 100)
    stream.feed_eof()
    with pytest.raises(docker.DockerFailure, match="docker_output_limit"):
        await docker._read(stream, 64)


@pytest.mark.anyio
async def test_cleanup_daemon_failure_unconfirmed(control, monkeypatch):
    async def inspect(name):
        raise docker.DockerFailure("docker_timeout")

    monkeypatch.setattr(control, "inspect", inspect)
    assert not await control.cleanup(RUN)
    assert await control.reap(RUN, True) == "unconfirmed"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("error", "docker_command_failed"),
        ("timeout", "docker_timeout"),
        ("flood", "docker_output_limit"),
    ],
)
async def test_execute_bounds_and_redacts(monkeypatch, mode, expected):
    class FakeProcess:
        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.returncode = None if mode == "timeout" else 1
            if mode != "timeout":
                self.stdout.feed_data(b"x" * 70000 if mode == "flood" else b"")
                self.stdout.feed_eof()
                self.stderr.feed_data(b"SECRET_VALUE")
                self.stderr.feed_eof()
            self.killed = False

        async def wait(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = FakeProcess()

    async def start(*args, **kwargs):
        assert kwargs["stdin"] == asyncio.subprocess.DEVNULL
        return process

    original_deadline = anyio.fail_after
    monkeypatch.setattr(docker.asyncio, "create_subprocess_exec", start)
    monkeypatch.setattr(docker.anyio, "fail_after", lambda _: original_deadline(0.01))
    with pytest.raises(docker.DockerFailure) as caught:
        await docker._execute(["docker"], {})
    assert caught.value.code == expected
    assert str(caught.value) == expected
    if mode == "timeout":
        assert process.killed


@pytest.mark.anyio
async def test_cancel_before_create_does_not_reach_daemon(control, monkeypatch):
    async def command(*args):
        pytest.fail("cancelled-before-create must not execute")

    monkeypatch.setattr(control, "command", command)
    with anyio.CancelScope() as scope:
        scope.cancel()
        await control.create(RUN, IMAGE, "pass", 0, 45)
    assert not control._created
