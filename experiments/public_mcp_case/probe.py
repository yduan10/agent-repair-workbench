"""P0-02 public issue probe: real SDK stdio, independent schema assertion.

Only the public synthetic case is exported. No secrets or user traces are read.
This experiment is not the product adapter's implementation or acceptance result.
"""

import asyncio
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path

COMMIT = "2118f14f8a19bc158d8a1cf90af58d85d187f849"
ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts/public-mcp-case"
SOURCE = ARTIFACTS / f"python-sdk-{COMMIT}"
sys.path[:0] = [str(SOURCE / "src"), str(SOURCE / "src/mcp-types")]

import mcp  # noqa: E402
import mcp_types  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402
from mcp import ClientSession, StdioServerParameters, stdio_client  # noqa: E402


class CaptureSession(ClientSession):
    """Defer output validation so the actual invalid result remains observable."""

    validation_deferred = False

    async def validate_tool_result(self, name: str, result: mcp_types.CallToolResult) -> None:
        self.validation_deferred = True


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def probe() -> dict[str, object]:
    for module in (mcp, mcp_types):
        if not Path(module.__file__).resolve().is_relative_to(SOURCE):
            raise RuntimeError("unexpected_sdk_source")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-B", str(Path(__file__).with_name("server.py"))],
        cwd=Path(__file__).parent,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    with (ARTIFACTS / "server-stderr.log").open("w", encoding="utf-8") as stderr:
        async with stdio_client(params, errlog=stderr) as (read, write):
            async with CaptureSession(read, write) as session:
                async with asyncio.timeout(20):
                    initialization = await session.initialize()
                    if initialization.protocol_version != "2025-11-25":
                        raise RuntimeError("unsupported_protocol")
                    listing = await session.list_tools()
                    tools = [tool for tool in listing.tools if tool.name == "tool"]
                    if len(tools) != 1 or listing.next_cursor is not None:
                        raise RuntimeError("unexpected_listing")
                    declaration = tools[0]
                    result = await session.call_tool("tool", {})
                    if not isinstance(result, mcp_types.CallToolResult):
                        raise RuntimeError("unexpected_result_type")
                    if result.is_error or not session.validation_deferred:
                        raise RuntimeError("no_success_result_to_validate")
    schema = declaration.output_schema
    if schema is None:
        raise RuntimeError("output_schema_missing")
    Draft202012Validator.check_schema(schema)
    violations = list(Draft202012Validator(schema).iter_errors(result.structured_content))
    # These assertions check the published failure, not the implementation's internals.
    reproduced = (
        sorted(schema.get("properties", {})) == ["user_id"]
        and result.structured_content == {"userId": 3, "doubled": 6}
        and any(error.validator == "required" for error in violations)
    )
    envelope = {
        "schema_version": 1,
        "tool": {
            "name": declaration.name,
            "input_schema": declaration.input_schema,
            "output_schema": schema,
        },
        "call": {"call_id": "public-case-local-1", "tool_name": "tool", "arguments": {}},
        "result": {
            "call_id": "public-case-local-1",
            "is_error": result.is_error,
            "structured_content": result.structured_content,
        },
    }
    evidence_path = ARTIFACTS / "synthetic-public-case-envelope.json"
    evidence_path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    return {
        "case": "modelcontextprotocol/python-sdk#3644",
        "source_commit": COMMIT,
        "case_input_kind": "public_synthetic_minimal_reproducer",
        "evidence_source": "real_stdio_sdk_normalized",
        "association": "local_id_after_sdk_dispatch",
        "wire_json_integrity": "not_checked",
        "protocol_version": initialization.protocol_version,
        "reproduced": reproduced,
        "violations": [
            {"validator": e.validator, "path": list(e.path), "schema_path": list(e.schema_path)}
            for e in violations
        ],
        "upstream_archive_sha256": digest(ARTIFACTS / "python-sdk.tar.gz"),
        "dependency_lock_sha256": digest(Path(__file__).with_name("uv.lock")),
        "server_script_sha256": digest(Path(__file__).with_name("server.py")),
        "evidence_sha256": digest(evidence_path),
        "python_version": sys.version.split()[0],
        "installed_dependencies": dict(
            sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())
        ),
        "notes": "SDK output validation deferred; independent required-field check fails.",
    }


if __name__ == "__main__":
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for previous in (
        "reproduction.json",
        "synthetic-public-case-envelope.json",
        "contract-report.json",
    ):
        (ARTIFACTS / previous).unlink(missing_ok=True)
    started = time.monotonic()
    try:
        outcome = asyncio.run(probe())
    except Exception as exc:
        # Raw third-party exception text may carry data; detailed failure is not public.
        (ARTIFACTS / "reproduction.json").write_text(
            json.dumps(
                {
                    "reproduced": False,
                    "error_code": "public_case_probe_failed",
                    "error_type": type(exc).__name__,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        print("public_case_probe_failed", file=sys.stderr)
        raise SystemExit(2) from None
    outcome["elapsed_seconds"] = round(time.monotonic() - started, 4)
    (ARTIFACTS / "reproduction.json").write_text(
        json.dumps(outcome, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"reproduced": outcome["reproduced"], "case": outcome["case"]}))
    raise SystemExit(0 if outcome["reproduced"] else 1)
