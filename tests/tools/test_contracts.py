import json

import pytest
from pydantic import TypeAdapter

from agent_workbench.controlled_tools.contracts import ReadSource, target_key
from agent_workbench.orchestration.codec import decode, decode_role
from agent_workbench.orchestration.policy import PolicyError

ID = "00000000-0000-0000-0000-000000000001"


def source(**changes):
    return {
        "tool": "read_source",
        "request_id": ID,
        "snapshot_id": "a" * 64,
        "relative_path": "src/中文.py",
        "start_line": 1,
        "end_line": 200,
        **changes,
    }


@pytest.mark.parametrize(
    "raw",
    [
        b'{"action":"conclude","action":"SECRET"}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b"[" * 21 + b"0" + b"]" * 21,
        b"[" * 10000 + b"0" + b"]" * 10000,
        b"\xff",
        b"{}" * 40000,
        b'{"tool":"read_source","request_id":"SECRET","args":{"x":1,"x":2}}',
    ],
)
def test_hostile_json_has_only_static_error(raw):
    with pytest.raises(PolicyError) as error:
        decode_role(raw, "diagnosis")
    assert str(error.value) in ("INVALID_MESSAGE", "MESSAGE_LIMIT_EXCEEDED")


@pytest.mark.parametrize(
    "change",
    [
        {"relative_path": "/etc/passwd"},
        {"relative_path": "src/../key"},
        {"relative_path": "src//tool"},
        {"relative_path": "./tool"},
        {"relative_path": "a\\b"},
        {"relative_path": "a\x00b"},
        {"start_line": True},
        {"start_line": "1"},
        {"end_line": 201},
        {"start_line": 10, "end_line": 9},
        {"root": "/"},
    ],
)
def test_read_source_boundaries(change):
    with pytest.raises(PolicyError):
        decode(json.dumps(source(**change)).encode(), TypeAdapter(ReadSource))


def test_canonical_key_unicode_and_request_identity():
    a = decode(json.dumps(source(), ensure_ascii=True).encode(), TypeAdapter(ReadSource))
    b = decode(
        json.dumps(source(request_id=ID[:-1] + "2"), ensure_ascii=False).encode(),
        TypeAdapter(ReadSource),
    )
    c = decode(json.dumps(source(end_line=199)).encode(), TypeAdapter(ReadSource))
    assert target_key(a) == target_key(b)
    assert target_key(a) != target_key(c)
