"""Independent P0-05a boundary regressions; no model/network/execution required."""

import json

import pytest
from pydantic import TypeAdapter

from agent_workbench.controlled_tools.contracts import ReadSource
from agent_workbench.orchestration.codec import decode
from agent_workbench.orchestration.contracts import TaskState
from agent_workbench.orchestration.policy import PolicyError, transition

ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize("revision", [False, 0.0, True, 1.0])
def test_cas_revision_requires_actual_integer(revision):
    state = TaskState(task_id=ID, intent="check_only")
    if revision == 1:
        state = transition(state, "checking", expected_revision=0)
    with pytest.raises(PolicyError):
        transition(state, "finished", expected_revision=revision, outcome="cancelled")


@pytest.mark.parametrize("codepoint", [0x80, 0x85, 0x9F])
def test_read_source_rejects_c1_controls(codepoint):
    payload = {
        "tool": "read_source",
        "request_id": ID,
        "snapshot_id": "a" * 64,
        "relative_path": f"src/a{chr(codepoint)}b.py",
        "start_line": 1,
        "end_line": 1,
    }
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode(json.dumps(payload).encode(), TypeAdapter(ReadSource))


@pytest.mark.parametrize("raw", [b"1e999", b"-1e999"])
def test_decoder_itself_rejects_non_finite_exponent(raw):
    with pytest.raises(PolicyError, match="^INVALID_MESSAGE$"):
        decode(raw, TypeAdapter(float))
