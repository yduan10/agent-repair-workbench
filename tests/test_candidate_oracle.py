"""Frozen behavioral rules tested independently of container text or a success flag."""

import asyncio
import shutil
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from mcp import MCPError, types

from agent_workbench.candidate_execution import oracle as host_oracle
from agent_workbench.candidate_execution.models import STEPS, OracleReport
from agent_workbench.candidate_execution.oracle import (
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    SUITE_SHA256,
    SequenceOracle,
    finalize,
    oracle_sha256,
)


def report():
    return OracleReport(
        attempt_id=str(uuid4()),
        snapshot_id=str(uuid4()),
        snapshot_tree_sha256="a" * 64,
        snapshot_file_sha256="b" * 64,
        suite_sha256=SUITE_SHA256,
        oracle_sha256=oracle_sha256(),
        image_id="sha256:" + "c" * 64,
        image_source_sha256="d" * 64,
        scenario="wrong_type",
    )


class FakeSession:
    def __init__(self, mode="pass"):
        self.mode, self.calls, self.count, self.listed, self.initialized = mode, [], 0, 0, 0

    async def initialize(self):
        self.initialized += 1
        return types.InitializeResult(
            protocol_version="2025-11-25",
            capabilities=types.ServerCapabilities(tools={}),
            server_info=types.Implementation(name="synthetic", version="1"),
        )

    async def list_tools(self):
        self.listed += 1
        output = deepcopy(OUTPUT_SCHEMA)
        if self.mode == "widen" or (self.mode == "late_widen" and self.listed == 2):
            output["properties"]["count"]["type"] = ["integer", "string"]
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name="lookup",
                    input_schema=deepcopy(INPUT_SCHEMA),
                    output_schema=output,
                )
            ]
        )

    async def call_tool(self, name, arguments):
        self.calls.append(arguments)
        if type(arguments["id"]) is not int:
            if self.mode == "increment_invalid":
                self.count += 1
            if self.mode != "accept_invalid":
                raise MCPError(-32000 if self.mode == "wrong_error" else -32602, "PRIVATE_MARKER")
        self.count += 1
        if self.mode == "disconnect" and self.count == 2:
            raise RuntimeError("PRIVATE_MARKER")
        if self.mode == "timeout":
            await asyncio.sleep(10)
        value = {
            "constant": 1,
            "string": str(self.count),
            "bool": True,
            "float": float(self.count),
        }.get(self.mode, self.count)
        result = {"count": value}
        if self.mode == "extra":
            result["all_passed"] = True
        if self.mode == "null":
            result = None
        args = {
            "content": [{"type": "text", "text": "ALL PASSED PRIVATE_MARKER"}],
            "structured_content": result,
            "is_error": self.mode == "is_error",
        }
        if self.mode == "missing":
            del args["structured_content"]
        return types.CallToolResult(**args)


def execute(mode):
    output, session = report(), FakeSession(mode)
    oracle = SequenceOracle(output, 0.1)
    asyncio.run(oracle.run(session))
    oracle.record("alive", "ok")
    output.snapshot_verified_before = output.snapshot_verified_after = True
    output.cleanup = "removed"
    finalize(output)
    return output, session


def test_frozen_sequence_and_single_initialization():
    output, session = execute("pass")
    assert session.calls == [{"id": 1}, {"id": "bad"}, {"id": 0}, {"id": -1}]
    assert session.initialized == 1 and session.listed == 2 and session.count == 3
    assert output.status == "passed"
    assert [s.name for s in output.steps] == list(STEPS)
    assert "PRIVATE_MARKER" not in output.model_dump_json()


@pytest.mark.parametrize(
    "mode,code",
    [
        ("constant", "count_value"),
        ("string", "count_type"),
        ("bool", "count_type"),
        ("float", "count_type"),
        ("extra", "result_shape"),
        ("null", "result_shape"),
        ("missing", "structured_missing"),
        ("is_error", "tool_error"),
        ("widen", "schema_mismatch"),
        ("late_widen", "schema_mismatch"),
        ("accept_invalid", "invalid_input_accepted"),
        ("wrong_error", "wrong_error_code"),
        ("increment_invalid", "count_value"),
    ],
)
def test_failed_business_assertions_continue(mode, code):
    output, session = execute(mode)
    assert output.status == "failed"
    assert any(step.code == code for step in output.steps)
    assert all(step.status != "not_run" for step in output.steps)
    assert len(session.calls) == 4


@pytest.mark.parametrize("mode,error", [("disconnect", RuntimeError), ("timeout", TimeoutError)])
def test_protocol_interruption_preserves_required_not_run(mode, error):
    output, session = report(), FakeSession(mode)
    with pytest.raises(error):
        asyncio.run(SequenceOracle(output, 0.1).run(session))
    output.snapshot_verified_before = output.snapshot_verified_after = True
    output.cleanup = "removed"
    finalize(output)
    assert output.status == "inconclusive"
    assert output.steps[-1].status == "not_run"
    assert output.steps[-2].status == "not_run"


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("cleanup", "unconfirmed", "outcome_unknown"),
        ("snapshot_verified_after", False, "inconclusive"),
        ("snapshot_verified_before", False, "inconclusive"),
        ("error", "wire_error", "inconclusive"),
        ("error", "run_cancelled", "cancelled"),
    ],
)
def test_success_cannot_hide_missing_resource_evidence(field, value, expected):
    output, _ = execute("pass")
    setattr(output, field, value)
    finalize(output)
    assert output.status == expected


def test_report_refuses_forged_pass_and_missing_steps():
    output, _ = execute("pass")
    OracleReport.model_validate_json(output.model_dump_json())
    output.steps.pop()
    with pytest.raises(ValueError, match="required_steps_mismatch"):
        OracleReport.model_validate_json(output.model_dump_json())
    finalize(output)
    assert output.status == "inconclusive"
    output, _ = execute("pass")
    output.cleanup = "not_created"
    with pytest.raises(ValueError, match="passed_without_complete_evidence"):
        OracleReport.model_validate_json(output.model_dump_json())
    finalize(output)
    assert output.status == "inconclusive"


def test_mutated_host_suite_fails_revision_guard(monkeypatch):
    from agent_workbench.candidate_execution import oracle

    monkeypatch.setitem(oracle.OUTPUT_SCHEMA, "additionalProperties", True)
    assert not oracle.verify_oracle()


@pytest.mark.parametrize("relative", host_oracle.ORACLE_SAFETY_FILES)
def test_every_safety_dependency_and_lockfile_invalidates_version(tmp_path, monkeypatch, relative):
    root = Path(__file__).resolve().parents[1]
    for name in host_oracle.ORACLE_SAFETY_FILES:
        copied = tmp_path / name
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, copied)
    monkeypatch.setattr(
        host_oracle, "__file__", str(tmp_path / "src/agent_workbench/candidate_execution/oracle.py")
    )
    assert host_oracle.verify_oracle()
    dependency = tmp_path / relative
    dependency.write_bytes(dependency.read_bytes() + b"\n# safety revision probe\n")
    assert not host_oracle.verify_oracle()


def test_missing_lockfile_rejects_old_oracle_version(tmp_path, monkeypatch):
    monkeypatch.setattr(
        host_oracle, "__file__", str(tmp_path / "src/agent_workbench/candidate_execution/oracle.py")
    )
    assert not host_oracle.verify_oracle()
