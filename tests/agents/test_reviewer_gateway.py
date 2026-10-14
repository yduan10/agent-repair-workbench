"""Independent local-only fault probes; no provider credentials or requests."""

import asyncio
import json
import time

from agent_workbench.model_gateway.gateway import PROFILE, Config, DeepSeekAdapter, decode_reply


def test_drip_feed_respects_whole_call_deadline():
    async def probe():
        writers = []

        async def serve(reader, writer):
            writers.append(writer)
            await reader.readuntil(b"\r\n\r\n")
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n"
            )
            await writer.drain()
            try:
                for _ in range(10):
                    writer.write(b" ")
                    await writer.drain()
                    await asyncio.sleep(0.025)
            except (ConnectionError, asyncio.CancelledError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(serve, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        adapter = DeepSeekAdapter(
            Config(f"http://127.0.0.1:{port}", "deepseek-flash", "synthetic-key", PROFILE)
        )
        start = time.monotonic()
        try:
            reply = await adapter.send(adapter.prepare("diagnosis", [], 8192), 0.1)
            elapsed = time.monotonic() - start
            assert reply.error == "MODEL_TIMEOUT", (reply.error, elapsed)
            assert elapsed < 0.2, elapsed
        finally:
            server.close()
            await server.wait_closed()
            for writer in writers:
                writer.close()

    asyncio.run(probe())


def test_bad_decision_utf8_does_not_erase_valid_usage():
    adapter = DeepSeekAdapter(
        Config("https://example.invalid", "deepseek-flash", "synthetic-key", PROFILE)
    )
    response = {
        "usage": {"prompt_tokens": 32, "completion_tokens": 16, "total_tokens": 48},
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "emit_decision", "arguments": "\ud800"},
                        }
                    ]
                },
            }
        ],
    }
    reply = decode_reply(json.dumps(response).encode(), adapter.prepare("diagnosis", [], 8192))
    assert reply.usage_known, reply
    assert reply.input_tokens == 32 and reply.output_tokens == 16
    assert reply.decision is None
