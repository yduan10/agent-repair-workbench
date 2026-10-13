"""Independent fixture regressions; never execute resource faults on the host."""

import errno
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "containers/p0_03/server.py"
SPEC = importlib.util.spec_from_file_location("review_fixture", SOURCE)
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class CapturedWrite(Exception):
    pass


@pytest.mark.parametrize("scenario", ["stdout_flood", "stdout_total_flood"])
def test_stdout_fault_reaches_intended_limit_before_json_error(monkeypatch, scenario):
    captured = []

    def capture(fd, data):
        captured.append((fd, data))
        raise CapturedWrite

    monkeypatch.setattr(server, "side_effect", lambda: 1)
    monkeypatch.setattr(server.os, "write", capture)
    with pytest.raises(CapturedWrite):
        server.call(
            3,
            {"name": "lookup", "arguments": {"id": 1}},
            SimpleNamespace(scenario=scenario, seed=0),
        )
    fd, frame = captured[0]
    assert fd == 1
    if scenario == "stdout_flood":
        assert b"\n" not in frame
    else:
        message = json.loads(frame)
        assert message["jsonrpc"] == "2.0"
        assert message["method"] == "notifications/message"
        assert message["params"]["level"] == "info"
        assert frame.endswith(b"\n") and len(frame) < 1024 * 1024


@pytest.mark.parametrize("error,expected", [(errno.EACCES, False), (errno.EROFS, True)])
def test_readonly_probe_does_not_confuse_dac_with_readonly(monkeypatch, error, expected):
    def denied(*args):
        raise OSError(error, "synthetic")

    monkeypatch.setattr(server.os, "open", denied)
    monkeypatch.setattr(server.Path, "iterdir", lambda _: iter([Path("lo")]))
    monkeypatch.setattr(server.Path, "read_text", lambda _: "32")
    assert server.policy_probe()["root_write_denied"] is expected
