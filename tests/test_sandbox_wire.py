"""P0-03 wire boundaries: limits apply before decoding, including chunked streams."""

import json

import pytest
from mcp import types

from agent_workbench.runner.models import SandboxConfig
from agent_workbench.runner.transport import (
    FRAME_LIMIT,
    STDERR_LIMIT,
    STDOUT_LIMIT,
    WireFailure,
    WireState,
)


def request(state, identifier=1):
    state.request(types.JSONRPCRequest(jsonrpc="2.0", id=identifier, method="ping"))


def response(identifier=1):
    return json.dumps({"jsonrpc": "2.0", "id": identifier, "result": {}}).encode() + b"\n"


def test_chunked_response_and_duplicate():
    state = WireState()
    request(state)
    raw = response()
    for byte in raw[:-1]:
        assert state.feed(bytes([byte])) == []
    assert len(state.feed(raw[-1:])) == 1
    with pytest.raises(WireFailure, match="duplicate_response_id"):
        state.feed(raw)


def test_valid_and_duplicate_in_same_chunk_never_released_as_success():
    state = WireState()
    request(state)
    with pytest.raises(WireFailure, match="duplicate_response_id"):
        state.feed(response() * 2)


@pytest.mark.parametrize(
    "raw,code",
    [
        (response(), "unmatched_response_id"),
        (b'{"jsonrpc":"2.0","id":1,"id":1,"result":{}}\n', "invalid_wire_frame"),
        (b"\xff\n", "invalid_wire_frame"),
        (b'{"jsonrpc":"2.0","id":1,"method":"run"}\n', "server_request_unsupported"),
    ],
)
def test_rejected_frames(raw, code):
    with pytest.raises(WireFailure, match=code):
        WireState().feed(raw)


def test_id_types_not_coerced():
    state = WireState()
    request(state, 1)
    with pytest.raises(WireFailure, match="unmatched_response_id"):
        state.feed(response("1"))


def test_no_newline_overflow_before_decode():
    state = WireState()
    for _ in range(FRAME_LIMIT // 4096):
        state.feed(b"\xff" * 4096)
    with pytest.raises(WireFailure, match="frame_limit_exceeded"):
        state.feed(b"\xff")


def test_total_byte_limit_for_valid_notifications():
    state = WireState()
    frame = (
        json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/message", "params": {"data": "x" * 32768}}
        ).encode()
        + b"\n"
    )
    with pytest.raises(WireFailure, match="stdout_limit_exceeded"):
        for _ in range(100):
            state.feed(frame)
    assert STDOUT_LIMIT < state.stdout_bytes <= STDOUT_LIMIT + len(frame)
    assert state.frames < 100


def test_stderr_limit_has_no_decoding():
    state = WireState()
    state.stderr(b"\xff" * STDERR_LIMIT)
    with pytest.raises(WireFailure, match="stderr_limit_exceeded"):
        state.stderr(b"\xff")


@pytest.mark.parametrize(
    "config",
    [
        {"command": "SECRET"},
        {"profile": "shell"},
        {"seed": True},
        {"seed": -1},
        {"lifetime": 46},
        {"scenario": "unknown"},
    ],
)
def test_config_is_strict(config):
    with pytest.raises(ValueError):
        SandboxConfig.model_validate(config)
