"""UI-08: copyable CLI commands shown in the web UI must parse with the real CLI.

Only static commands are checked; templated ones (case/intent/IDs) are covered by their own tests.
"""

import argparse
import re
import shlex
from pathlib import Path

import pytest

from agent_workbench.repair_runtime.cli import configure as configure_repair
from agent_workbench.run_store.cli import configure as configure_runs

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
PREFIX = ["uv", "run", "--frozen", "agent-workbench"]


class _Strict(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Strict(prog="agent-workbench")
    commands = parser.add_subparsers(dest="command", required=True)
    configure_repair(commands.add_parser("repair"))
    configure_runs(commands.add_parser("runs"))
    return parser


def _constant(path: str, name: str) -> str:
    source = (FRONTEND / path).read_text(encoding="utf-8")
    match = re.search(rf'export const {name} =\s*"([^"]+)"', source)
    assert match, f"{name} not found in {path}"
    return match.group(1)


@pytest.mark.parametrize(
    ("path", "name"),
    [("lib/repairs.ts", "REPAIR_COMMAND"), ("lib/analysis-runs.ts", "ANALYSIS_INIT_COMMAND")],
)
def test_static_ui_command_parses(path: str, name: str) -> None:
    argv = shlex.split(_constant(path, name))
    assert argv[: len(PREFIX)] == PREFIX
    _parser().parse_args(argv[len(PREFIX) :])


def test_landing_page_reuses_repair_command() -> None:
    # A second hard-coded copy is how the landing page drifted to an unsupported --case flag.
    page = (FRONTEND / "app/page.tsx").read_text(encoding="utf-8")
    assert "agent-workbench repair" not in page
    assert "REPAIR_COMMAND" in page


def test_parser_rejects_unsupported_flag() -> None:
    with pytest.raises(ValueError):
        _parser().parse_args(["repair", "--case", "arbitrary_project", "--mode", "three_role"])
