"""Independent B3 deployment failure tests; never call the host launchctl."""

import importlib.util
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "b3_local_service_review", ROOT / "ops/local_service.py"
)
assert SPEC and SPEC.loader
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)


@pytest.fixture
def local(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    private = root / "artifacts/local-service"
    private.mkdir(parents=True)
    env = private / "model-env.json"
    env.write_text(json.dumps({"AWB_MODEL_API_KEY": "review-synthetic-secret"}))
    env.chmod(0o600)
    for relative in (".venv/bin/python", "frontend/.next/BUILD_ID"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(service, "ROOT", root)
    monkeypatch.setattr(service, "LOCAL", private)
    monkeypatch.setattr(service.sys, "platform", "darwin")
    monkeypatch.setattr(service.shutil, "which", lambda _name: "/test/bin/node")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    loaded = set()
    actions = []
    failure = {"bootstrap": None, "bootout": None}

    def run(argv, **kwargs):
        actions.append(argv)
        action = argv[1]
        if action == "print":
            code = 0 if argv[-1].split("/")[-1] in loaded else 113
        elif action == "bootstrap":
            label = plistlib.loads(Path(argv[-1]).read_bytes())["Label"]
            code = 5 if failure["bootstrap"] == label else 0
            if code == 0:
                loaded.add(label)
        elif action == "bootout":
            label = argv[-1].split("/")[-1]
            code = 5 if failure["bootout"] == label else 0
            if code == 0:
                loaded.discard(label)
        else:
            raise AssertionError(f"Unexpected test command: {action}")
        if code and kwargs.get("check"):
            raise subprocess.CalledProcessError(code, argv)
        return subprocess.CompletedProcess(
            argv, code, stdout=str(root).encode() if code == 0 else b"", stderr=b""
        )

    monkeypatch.setattr(service.subprocess, "run", run)

    def command(name):
        monkeypatch.setattr(sys, "argv", ["local_service.py", name])
        return service.main()

    return SimpleNamespace(
        root=root,
        home=home,
        env=env,
        loaded=loaded,
        actions=actions,
        failure=failure,
        command=command,
    )


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o660])
def test_rejects_environment_readable_by_other_users(local, mode):
    local.env.chmod(mode)
    with pytest.raises(ValueError, match="private_environment_required"):
        service.read_environment(local.env)


def test_rejects_symlink_environment(local):
    pointer = local.env.with_name("symlink.json")
    pointer.symlink_to(local.env)
    with pytest.raises(ValueError, match="private_environment_required"):
        service.read_environment(pointer)


@pytest.mark.parametrize("value", [{"OTHER": "x"}, {"AWB_MODEL_NAME": "a\x00b"}, []])
def test_rejects_invalid_environment(local, value):
    local.env.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        service.read_environment(local.env)


def test_rejects_overlong_environment(local):
    local.env.write_text("x" * 16385)
    with pytest.raises(ValueError, match="environment_too_large"):
        service.read_environment(local.env)


def test_plists_have_no_credentials_and_loopback_web_binding(local):
    local.command("install")
    folder = local.home / "Library/LaunchAgents"
    assert local.loaded == set(service.LABELS.values())
    for path in folder.iterdir():
        payload = path.read_bytes()
        assert b"review-synthetic-secret" not in payload
        assert b"AWB_MODEL_API_KEY" not in payload
        assert path.stat().st_mode & 0o777 == 0o600
    web = plistlib.loads((folder / f"{service.LABELS['web']}.plist").read_bytes())
    assert web["ProgramArguments"][-4:] == ["--hostname", "127.0.0.1", "--port", "3010"]
    assert web["ExitTimeOut"] >= 600


def test_late_plist_conflict_does_not_start_api(local):
    folder = local.home / "Library/LaunchAgents"
    folder.mkdir(parents=True)
    (folder / f"{service.LABELS['web']}.plist").write_bytes(plistlib.dumps({"Label": "other"}))
    with pytest.raises(ValueError):
        local.command("install")
    assert local.loaded == set()
    assert not any(argv[1] == "bootstrap" for argv in local.actions)


def test_second_bootstrap_failure_rolls_back_only_new_services(local):
    local.failure["bootstrap"] = service.LABELS["web"]
    with pytest.raises((ValueError, RuntimeError, subprocess.CalledProcessError)):
        local.command("install")
    assert local.loaded == set()


def test_existing_late_service_is_not_disrupted_or_partially_restarted(local):
    local.loaded.add(service.LABELS["web"])
    with pytest.raises(ValueError):
        local.command("install")
    assert local.loaded == {service.LABELS["web"]}
    assert not any(argv[1] in ("bootstrap", "bootout") for argv in local.actions)


def test_stop_failure_is_visible_and_preserves_other_failure_information(local):
    local.command("install")
    local.failure["bootout"] = service.LABELS["api"]
    with pytest.raises((ValueError, RuntimeError, subprocess.CalledProcessError)):
        local.command("stop")
    assert local.loaded == {service.LABELS["api"]}


def test_stop_refuses_other_checkout_configuration(local):
    local.command("install")
    folder = local.home / "Library/LaunchAgents"
    path = folder / f"{service.LABELS['api']}.plist"
    value = plistlib.loads(path.read_bytes())
    value["WorkingDirectory"] = str(local.root.with_name("other-checkout"))
    path.write_bytes(plistlib.dumps(value))
    local.actions.clear()
    with pytest.raises(ValueError):
        local.command("stop")
    assert not any(argv[1] == "bootout" for argv in local.actions)


def test_read_environment_rejects_wrong_owner(local, monkeypatch):
    monkeypatch.setattr(service.os, "getuid", lambda: os.stat(local.env).st_uid + 1)
    with pytest.raises(ValueError, match="private_environment_required"):
        service.read_environment(local.env)


def test_launchctl_query_error_never_means_unregistered(local, monkeypatch):
    calls = []

    def unavailable(argv, **kwargs):
        calls.append(argv)
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(5, argv)
        return subprocess.CompletedProcess(argv, 5, stdout=b"", stderr=b"")

    monkeypatch.setattr(service.subprocess, "run", unavailable)
    with pytest.raises((ValueError, RuntimeError, subprocess.CalledProcessError)):
        local.command("install")
    assert calls
    assert all(argv[1] == "print" for argv in calls)


def test_failed_rollback_remains_visible(local):
    local.failure["bootstrap"] = service.LABELS["web"]
    local.failure["bootout"] = service.LABELS["api"]
    with pytest.raises(ValueError, match="install_rollback_incomplete"):
        local.command("install")
    assert local.loaded == {service.LABELS["api"]}


def test_stop_is_idempotent_when_already_absent(local):
    local.command("stop")
    assert local.loaded == set()
    assert not any(argv[1] == "bootout" for argv in local.actions)


def test_api_launcher_uses_fixed_loopback_and_private_runtime_config(local, monkeypatch):
    observed = {}

    def start(*args, **kwargs):
        observed.update(args=args, kwargs=kwargs, env=dict(service.os.environ))

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=start))
    monkeypatch.setattr(service.os, "environ", {})
    local.command("serve-api")
    assert observed["args"] == ("agent_workbench.api:app",)
    assert observed["kwargs"] == {"host": "127.0.0.1", "port": 8030, "access_log": False}
    assert observed["env"]["AWB_STATE_DIR"] == str(local.root / "artifacts/run-store")
    assert observed["env"]["AWB_MODEL_API_KEY"] == "review-synthetic-secret"
    assert local.actions == []


def test_stop_waits_for_launchd_registration_to_disappear(local, monkeypatch):
    local.command("install")
    original = service.subprocess.run
    pending = {}

    def delayed(argv, **kwargs):
        label = argv[-1].split("/")[-1]
        if argv[1] == "print" and pending.get(label, 0):
            pending[label] -= 1
            return subprocess.CompletedProcess(argv, 0, stdout=str(local.root).encode())
        result = original(argv, **kwargs)
        if argv[1] == "bootout":
            pending[label] = 2
        return result

    monkeypatch.setattr(service.subprocess, "run", delayed)
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    local.command("stop")
    assert local.loaded == set()
    assert all(value == 0 for value in pending.values())


def test_stop_does_not_succeed_if_registration_never_disappears(local, monkeypatch):
    local.command("install")
    original = service.subprocess.run

    def stuck(argv, **kwargs):
        if argv[1] == "bootout":
            return subprocess.CompletedProcess(argv, 0)
        return original(argv, **kwargs)

    monkeypatch.setattr(service.subprocess, "run", stuck)
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    with pytest.raises(ValueError, match="service_stop_failed"):
        local.command("stop")
    assert local.loaded == set(service.LABELS.values())


def test_install_rollback_waits_then_reports_original_bootstrap_failure(local, monkeypatch):
    local.failure["bootstrap"] = service.LABELS["web"]
    original = service.subprocess.run
    pending = {}

    def delayed(argv, **kwargs):
        label = argv[-1].split("/")[-1]
        if argv[1] == "print" and pending.get(label, 0):
            pending[label] -= 1
            return subprocess.CompletedProcess(argv, 0, stdout=str(local.root).encode())
        result = original(argv, **kwargs)
        if argv[1] == "bootout":
            pending[label] = 2
        return result

    monkeypatch.setattr(service.subprocess, "run", delayed)
    monkeypatch.setattr(service.time, "sleep", lambda _: None)
    with pytest.raises(subprocess.CalledProcessError):
        local.command("install")
    assert local.loaded == set()
    assert all(value == 0 for value in pending.values())
