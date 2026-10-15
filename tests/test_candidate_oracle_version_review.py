"""Independent B2 revision binding: copied host code, no production mutation or execution."""

import shutil
from pathlib import Path

import pytest

from agent_workbench.candidate_execution import oracle

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "relative",
    [
        "src/agent_workbench/runner/docker.py",
        "src/agent_workbench/runner/service.py",
        "src/agent_workbench/candidates/snapshots.py",
        "src/agent_workbench/candidates/contracts.py",
        "src/agent_workbench/checker.py",
        "src/agent_workbench/mcp_config.py",
        "uv.lock",
    ],
)
def test_safety_dependency_change_invalidates_oracle_version(tmp_path, monkeypatch, relative):
    shutil.copytree(
        ROOT / "src", tmp_path / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    shutil.copyfile(ROOT / "uv.lock", tmp_path / "uv.lock")
    copied_oracle = tmp_path / "src/agent_workbench/candidate_execution/oracle.py"
    monkeypatch.setattr(oracle, "__file__", str(copied_oracle))
    frozen = oracle.oracle_sha256()
    monkeypatch.setattr(oracle, "ORACLE_SHA256", frozen)
    assert oracle.verify_oracle()
    dependency = tmp_path / relative
    dependency.write_bytes(dependency.read_bytes() + b"\n# revision binding probe\n")
    assert not oracle.verify_oracle(), f"unbound safety dependency: {relative}"
