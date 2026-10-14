"""P0-05b repair role; shared transport and policy remain in the host."""

from pathlib import Path

from agent_workbench.orchestration.role import RoleAgent


def build() -> RoleAgent:
    return RoleAgent("repair", (Path(__file__).parent / "prompts" / "v1.txt").read_text())
