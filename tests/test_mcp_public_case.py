"""Opt-in historical integration, never fetches or installs source automatically."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_workbench.mcp_models import MCPReport

pytestmark = [
    pytest.mark.public_case,
    pytest.mark.skipif(
        os.environ.get("AWB_PUBLIC_CASE") != "1", reason="run explicit public case gate"
    ),
]
ROOT = Path(__file__).resolve().parents[1]


def test_fixed_public_issue_through_product_cli():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_workbench",
            "mcp-check",
            "--server-config",
            "examples/mcp/public-server.json",
            "--case",
            "examples/mcp/public-case.json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout
    assert not result.stderr
    report = MCPReport.model_validate_json(result.stdout)
    assert report.adapter_outcome == "completed"
    assert report.source.server_revision == "2118f14f8a19bc158d8a1cf90af58d85d187f849"
    assert len(report.source.source_tree_sha256) == 64
    assert report.source.protocol_version == "2025-11-25"
    assert report.contract_report.status == "failed"
    assert any(
        f.code == "output_schema_violation" and f.schema_path == "/required"
        for f in report.contract_report.findings
    )
    assert report.source.wire_json_integrity == "not_checked"
