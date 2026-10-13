"""P0-02 synthetic, read-only MCP stdio scenarios; never a public bug fixture."""

import argparse
import asyncio
import os
import sys
from typing import Any

import anyio
from mcp import MCPError, types
from mcp.server.lowlevel.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.shared.message import SessionMessage

SCENARIOS = (
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
)
INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "integer"}},
    "required": ["id"],
    "additionalProperties": False,
}
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"count": {"type": "integer"}},
    "required": ["count"],
    "additionalProperties": False,
}


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "fixture_invalid_arguments\n")


async def serve(scenario: str) -> None:
    calls = 0

    def tool(name: str = "lookup") -> types.Tool:
        if scenario in ("no_output_schema", "resource_content"):
            return types.Tool(name=name, input_schema=INPUT_SCHEMA)
        output_schema = OUTPUT_SCHEMA
        if scenario == "unsupported_schema":
            output_schema = {"type": "object", "$ref": "#/$defs/example"}
        elif scenario == "invalid_schema":
            output_schema = {"type": "object", "required": ["count", "count"]}
        return types.Tool(name=name, input_schema=INPUT_SCHEMA, output_schema=output_schema)

    async def list_tools(
        context: ServerRequestContext[None], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        cursor = params.cursor if params else None
        if scenario == "cursor_loop":
            return types.ListToolsResult(tools=[], next_cursor="loop")
        if scenario == "duplicate_tools":
            return types.ListToolsResult(tools=[tool(), tool()])
        if scenario == "paginated" and cursor is None:
            return types.ListToolsResult(tools=[tool("page_one")], next_cursor="page_two")
        if cursor is not None and not (scenario == "paginated" and cursor == "page_two"):
            raise MCPError(-32602, "fixture_invalid_cursor")
        return types.ListToolsResult(tools=[tool()])

    async def call_tool(
        context: ServerRequestContext[None], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        nonlocal calls
        calls += 1
        # Count fixed markers to prove execution; never echo arguments or environment.
        print("fixture_call", file=sys.stderr, flush=True)
        if scenario == "crash":
            os._exit(17)
        if scenario == "timeout":
            await asyncio.sleep(60)
        if scenario == "protocol_error":
            raise MCPError(-32602, "fixture_protocol_error")
        if params.name not in ("lookup", "page_one"):
            raise MCPError(-32602, "fixture_unknown_tool")
        if scenario == "resource_content":
            return types.CallToolResult(
                content=[
                    types.ResourceLink(
                        type="resource_link",
                        name="synthetic",
                        uri="https://example.invalid/never-fetch",
                    )
                ]
            )
        if scenario == "oversized_content":
            return types.CallToolResult(
                content=[types.TextContent(type="text", text="x" * (1024 * 1024))],
                structured_content={"count": 1},
            )
        if scenario == "missing_content":
            return types.CallToolResult(
                content=[types.TextContent(type="text", text='{"count":1}')]
            )
        if scenario == "null_content":
            return types.CallToolResult(content=[], structured_content=None)
        if scenario == "tool_error":
            return types.CallToolResult(content=[], is_error=True)
        count: int | str = "synthetic_wrong_type" if scenario == "wrong_type" else calls
        return types.CallToolResult(content=[], structured_content={"count": count})

    server: Server[None] = Server(
        "awb-contract-fixture",
        version="1.0.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
    async with stdio_server() as (read, write):
        if scenario not in ("null_content", "unexpected_protocol"):
            await server.run(read, write, server.create_initialization_options())
            return
        # SDK 2.3's server serialization drops None. Inject this deliberate wire
        # fault after that serialization so the client sees explicit JSON null.
        sender, receiver = anyio.create_memory_object_stream[SessionMessage](0)

        async def inject_wire_fault() -> None:
            async with receiver:
                async for message in receiver:
                    response = message.message
                    if isinstance(response, types.JSONRPCResponse):
                        if scenario == "null_content" and "content" in response.result:
                            response.result["structuredContent"] = None
                        if (
                            scenario == "unexpected_protocol"
                            and "protocolVersion" in response.result
                        ):
                            response.result["protocolVersion"] = "2024-11-05"
                    await write.send(message)

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(inject_wire_fault)
            async with sender:
                await server.run(read, sender, server.create_initialization_options())


if __name__ == "__main__":
    parser = SafeParser()
    parser.add_argument("--scenario", choices=SCENARIOS, default="pass")
    asyncio.run(serve(parser.parse_args().scenario))
