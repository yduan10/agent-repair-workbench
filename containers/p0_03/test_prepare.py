"""P0-03 unit checks: no Docker daemon, network, container or host side effects."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def load(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("p003_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("prepare")
server = load("server")
IMAGE = "sha256:" + "a" * 64


def inspected_image(image_id=IMAGE, **overrides):
    config = {
        "Entrypoint": list(prepare.EXPECTED_ENTRYPOINT),
        "User": "65532:65532",
        "WorkingDir": "/tmp",
        "Volumes": None,
        "Env": list(prepare.EXPECTED_ENV),
    }
    config.update(overrides)
    return json.dumps([{"Id": image_id, "Config": config}])


def write_iid(argv, value=IMAGE):
    Path(argv[argv.index("--iidfile") + 1]).write_text(value + "\n")


@pytest.fixture
def source(tmp_path, monkeypatch):
    directory = tmp_path / "fixture"
    directory.mkdir()
    for name in prepare.SOURCE_FILES:
        (directory / name).write_text(name + " fixture")
    monkeypatch.setattr(prepare, "SOURCE_DIR", directory)
    monkeypatch.setattr(prepare, "PROJECT_ROOT", tmp_path)
    original_hash = prepare.source_sha256
    monkeypatch.setattr(prepare, "source_sha256", lambda: original_hash(directory))
    return directory


def test_hash_algorithm_and_tamper(tmp_path):
    for name in prepare.SOURCE_FILES:
        (tmp_path / name).write_text(name)
    expected = hashlib.sha256(
        b"\0".join(name.encode() + b"\0" + name.encode() for name in prepare.SOURCE_FILES)
    ).hexdigest()
    assert prepare.source_sha256(tmp_path) == expected
    (tmp_path / "server.py").write_text("changed")
    assert prepare.source_sha256(tmp_path) != expected


def test_source_symlink_rejected(tmp_path):
    (tmp_path / "target").write_text("ignored")
    (tmp_path / "Dockerfile").symlink_to(tmp_path / "target")
    with pytest.raises(ValueError, match="source_unavailable"):
        prepare.source_sha256(tmp_path)


def test_build_offline_minimal_context_atomic_manifest(source, monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert kwargs["check"] is True
        assert kwargs["timeout"] <= 120
        if argv[1] == "build":
            context = Path(argv[-1])
            assert {p.name for p in context.iterdir()} == {"Dockerfile", "server.py"}
            assert "--network=none" in argv
            assert "--pull=false" in argv
            assert f"BASE={prepare.BASE_DIGEST}" in argv
            assert argv[argv.index("--tag") + 1] == "awb-p0-03:local"
            iidfile = Path(argv[argv.index("--iidfile") + 1])
            assert iidfile.parent == context.parent
            assert not iidfile.is_relative_to(context)
            write_iid(argv)
        return SimpleNamespace(stdout=inspected_image())

    monkeypatch.setattr(prepare.subprocess, "run", run)
    result = prepare.prepare()
    assert calls[0][0] == ["docker", "image", "inspect", prepare.BASE_DIGEST]
    assert calls[-1][0] == ["docker", "image", "inspect", IMAGE]
    assert result == {
        "image_id": IMAGE,
        "source_sha256": prepare.source_sha256(),
        "base_digest": prepare.BASE_DIGEST,
    }
    artifacts = prepare.PROJECT_ROOT / "artifacts"
    assert json.loads((artifacts / "p0-03-image.json").read_text()) == result
    assert len(list(artifacts.iterdir())) == 1


@pytest.mark.parametrize(
    "failure", ["missing_base", "build_failure", "bad_image", "changed_source"]
)
def test_prepare_failure_never_replaces_manifest(source, monkeypatch, failure):
    artifacts = prepare.PROJECT_ROOT / "artifacts"
    artifacts.mkdir()
    manifest = artifacts / "p0-03-image.json"
    manifest.write_text("prior")
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if failure == "missing_base":
            raise subprocess.CalledProcessError(1, argv)
        if argv[1] == "build" and failure == "build_failure":
            raise subprocess.CalledProcessError(1, argv)
        if argv[1] == "build" and failure == "changed_source":
            (source / "server.py").write_text("mutated")
        if argv[1] == "build":
            write_iid(argv, "bad" if failure == "bad_image" else IMAGE)
        return SimpleNamespace(stdout=inspected_image())

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        prepare.prepare()
    assert manifest.read_text() == "prior"
    if failure == "missing_base":
        assert len(calls) == 1


def test_concurrent_retag_does_not_select_another_build(source, monkeypatch):
    other = "sha256:" + "b" * 64
    tag_target = IMAGE
    inspections = []

    def run(argv, **kwargs):
        nonlocal tag_target
        if argv[1] == "build":
            write_iid(argv)
            tag_target = other  # Another build moves the tag before this build is inspected.
            return SimpleNamespace(stdout="")
        inspections.append(argv[-1])
        selected = tag_target if argv[-1] == prepare.IMAGE_TAG else argv[-1]
        return SimpleNamespace(stdout=inspected_image(selected))

    monkeypatch.setattr(prepare.subprocess, "run", run)
    assert prepare.prepare()["image_id"] == IMAGE
    assert inspections == [prepare.BASE_DIGEST, IMAGE]
    assert tag_target == other


@pytest.mark.parametrize(
    "config",
    [
        {"Entrypoint": ["sh", "-c", "untrusted"]},
        {"Entrypoint": None},
        {"User": "root"},
        {"WorkingDir": "/root"},
        {"Volumes": {"/data": {}}},
        {"Env": list(prepare.EXPECTED_ENV) + ["EXTRA=untrusted"]},
        {"Env": list(prepare.EXPECTED_ENV) + [prepare.EXPECTED_ENV[0]]},
        {"Env": ["PATH=/malicious/bin"]},
        {"Env": None},
        {"Env": [42]},
    ],
)
def test_bad_config_never_replaces_manifest(source, monkeypatch, config):
    artifacts = prepare.PROJECT_ROOT / "artifacts"
    artifacts.mkdir()
    manifest = artifacts / "p0-03-image.json"
    manifest.write_text("prior")

    def run(argv, **kwargs):
        if argv[1] == "build":
            write_iid(argv)
        return SimpleNamespace(stdout=inspected_image(**config))

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises(ValueError, match="invalid_image_config"):
        prepare.prepare()
    assert manifest.read_text() == "prior"


@pytest.mark.parametrize(
    "payload", ["{}", "[]", "[null]", "invalid", inspected_image("sha256:" + "b" * 64)]
)
def test_invalid_inspection_refuses_manifest(source, monkeypatch, payload):
    def run(argv, **kwargs):
        if argv[1] == "build":
            write_iid(argv)
        return SimpleNamespace(stdout=payload)

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises(ValueError):
        prepare.prepare()
    assert not (prepare.PROJECT_ROOT / "artifacts" / "p0-03-image.json").exists()


@pytest.mark.parametrize("value", [None, "sha256:" + "a" * 12, "x" * 129])
def test_missing_or_incomplete_iid_never_falls_back_to_tag(source, monkeypatch, value):
    inspected = []

    def run(argv, **kwargs):
        if argv[1] == "build" and value is not None:
            write_iid(argv, value)
        elif argv[1] == "image":
            inspected.append(argv[-1])
        return SimpleNamespace(stdout=inspected_image())

    monkeypatch.setattr(prepare.subprocess, "run", run)
    with pytest.raises(ValueError, match="invalid_image_id"):
        prepare.prepare()
    assert inspected == [prepare.BASE_DIGEST]


@pytest.mark.parametrize(
    "error,code",
    [
        (OSError("SECRET_VALUE"), "image_prepare_failed"),
        (subprocess.TimeoutExpired(["SECRET_VALUE"], 120), "image_prepare_timeout"),
    ],
)
def test_error_output_redacted(monkeypatch, capsys, error, code):
    monkeypatch.setattr(sys, "argv", ["prepare.py"])

    def fail():
        raise error

    monkeypatch.setattr(prepare, "prepare", fail)
    assert prepare.main() == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert json.loads(out.err) == {"code": code}
    assert "SECRET_VALUE" not in out.err


def test_unknown_arguments_do_not_execute(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["prepare.py", "SECRET_VALUE"])
    monkeypatch.setattr(prepare, "prepare", lambda: pytest.fail("must not execute"))
    assert prepare.main() == 2
    assert json.loads(capsys.readouterr().err) == {"code": "invalid_arguments"}


def test_fixture_schema_and_protocol(monkeypatch):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "lookup", "arguments": {"id": 7}},
        },
    ]
    data = b"".join(json.dumps(request).encode() + b"\n" for request in requests)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(data)))
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(server, "side_effect", lambda: 1)
    assert server.serve(SimpleNamespace(scenario="pass", seed=0)) == 0
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [r["id"] for r in responses] == [1, 2, 3]
    assert responses[0]["result"]["protocolVersion"] == "2025-11-25"
    assert responses[1]["result"]["tools"][0]["name"] == "lookup"
    assert responses[2]["result"]["structuredContent"] == {"count": 1}


@pytest.mark.parametrize("scenario", ["pass", "duplicate_result", "tool_error"])
def test_fixture_side_effect_once_even_duplicate(monkeypatch, scenario):
    effects, replies = [], []
    monkeypatch.setattr(server, "side_effect", lambda: effects.append(1) or 1)
    monkeypatch.setattr(
        server, "emit", lambda identifier, result: replies.append((identifier, result))
    )
    server.call(
        5, {"name": "lookup", "arguments": {"id": 1}}, SimpleNamespace(scenario=scenario, seed=0)
    )
    assert len(effects) == 1
    assert len(replies) == (2 if scenario == "duplicate_result" else 1)
    assert all(identifier == 5 for identifier, _ in replies)
    assert replies[0][1]["isError"] is (scenario == "tool_error")


@pytest.mark.parametrize("arguments", [{"id": True}, {}, {"id": 1, "extra": 2}, []])
def test_invalid_call_has_no_side_effect(monkeypatch, arguments):
    monkeypatch.setattr(server, "side_effect", lambda: pytest.fail("unexpected side effect"))
    errors = []
    monkeypatch.setattr(server, "reject", lambda *args: errors.append(args))
    server.call(
        1, {"name": "lookup", "arguments": arguments}, SimpleNamespace(scenario="pass", seed=0)
    )
    assert errors == [(1, -32602)]


@pytest.mark.parametrize("value", ["-1", "2147483648", "bad"])
def test_seed_rejects_invalid(value):
    with pytest.raises((ValueError, argparse.ArgumentTypeError)):
        server.bounded_int(0, 2**31 - 1)(value)


@pytest.mark.parametrize("status,expected", [(None, 124), (-9, 137), (72, 72)])
def test_supervisor_watchdog_or_worker_exit(monkeypatch, status, expected):
    monkeypatch.setattr(sys, "argv", ["server.py", "--lifetime", "5"])
    monkeypatch.setattr(server.Path, "is_file", lambda _: True)
    monkeypatch.setattr(server.os, "getpid", lambda: 1)
    ticks = iter([0.0, 1.0, 6.0])
    monkeypatch.setattr(server.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    monkeypatch.setattr(server.signal, "signal", lambda *args: None)
    monkeypatch.setattr(
        server.subprocess, "Popen", lambda *args, **kw: SimpleNamespace(poll=lambda: status)
    )

    def hard_exit(code):
        raise SystemExit(code)

    monkeypatch.setattr(server.os, "_exit", hard_exit)
    if status is None:
        with pytest.raises(SystemExit) as caught:
            server.main()
        assert caught.value.code == expected
    else:
        assert server.main() == expected


def test_fixture_invalid_cli_is_redacted(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["server.py", "--seed", "SECRET_VALUE"])
    with pytest.raises(SystemExit) as caught:
        server.main()
    assert caught.value.code == 2
    assert capsys.readouterr().err == "invalid_arguments\n"
