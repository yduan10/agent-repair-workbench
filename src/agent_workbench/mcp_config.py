"""P0-02 reviewed profiles: JSON cannot select a shell, executable, cwd or env."""

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue

from agent_workbench.models import StrictModel

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_COMMIT = "2118f14f8a19bc158d8a1cf90af58d85d187f849"
PUBLIC_ARCHIVE_SHA256 = "c860806fd728927747fdc0b9624b824d545e48e4199e1be9cc94906f6e44aba9"
Scenario = Literal[
    "pass",
    "oversized_content",
    "resource_content",
    "wrong_type",
    "missing_content",
    "null_content",
    "no_output_schema",
    "tool_error",
    "protocol_error",
    "paginated",
    "cursor_loop",
    "duplicate_tools",
    "timeout",
    "crash",
    "unsupported_schema",
    "invalid_schema",
    "unexpected_protocol",
]


class ServerConfig(StrictModel):
    profile: Literal["contract-fixture", "public-sdk-3644"]
    scenario: Scenario = "pass"


class CallCase(StrictModel):
    case_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
    tool: Annotated[str, Field(min_length=1, max_length=128)]
    arguments: dict[str, JsonValue]


class PublicVerification(StrictModel):
    code: Literal["source_verified"]
    commit: str
    archive_sha256: str
    lock_sha256: str
    source_tree_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_files_verified: Annotated[int, Field(gt=0)]
    source_modified: Literal[False]


@dataclass(frozen=True)
class Launch:
    command: Path
    script: Path
    args: tuple[str, ...]
    cwd: Path
    dependencies: Path


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def resolve_launch(config: ServerConfig) -> Launch:
    if config.profile == "contract-fixture":
        script = ROOT / "tests/fixtures/mcp_server.py"
        return Launch(
            Path(sys.executable).absolute(),
            script,
            ("-I", "-B", str(script), "--scenario", config.scenario),
            script.parent,
            ROOT / "uv.lock",
        )
    if config.scenario != "pass":
        raise ValueError("public_profile_has_no_scenarios")
    directory = ROOT / "experiments/public_mcp_case"
    command = directory / ".venv/bin/python"
    script = directory / "server.py"
    if not command.is_file() or not script.is_file():
        raise ValueError("profile_not_prepared")
    return Launch(command, script, ("-I", "-B", str(script)), directory, directory / "uv.lock")
