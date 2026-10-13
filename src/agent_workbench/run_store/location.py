"""One local state directory shared by CLI and the read-only HTTP adapter."""

import os
from pathlib import Path

from agent_workbench.mcp_config import ROOT


def state_directory() -> Path:
    return Path(os.environ.get("AWB_STATE_DIR", str(ROOT / "artifacts/run-store")))
