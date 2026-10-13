"""Bounded raw-byte transport. Never log subprocess payloads or parse exceptions."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import anyio
from anyio.abc import Process
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp import types
from mcp.shared.message import SessionMessage
from mcp_types import jsonrpc_message_adapter

from agent_workbench.checker import parse_json_bytes

STDOUT_LIMIT = 2 * 1024 * 1024
FRAME_LIMIT = 1024 * 1024
STDERR_LIMIT = 64 * 1024
type Streams = tuple[
    MemoryObjectReceiveStream[SessionMessage | Exception], MemoryObjectSendStream[SessionMessage]
]


class WireFailure(Exception):
    """Contains only an application-defined error code."""


@dataclass
class WireState:
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    frames: int = 0
    error: str | None = None
    pending: set[tuple[type, str | int]] = field(default_factory=set)
    seen: set[tuple[type, str | int]] = field(default_factory=set)
    buffer: bytearray = field(default_factory=bytearray)

    def fail(self, code: str) -> None:
        if self.error is None:
            self.error = code

    def request(self, message: types.JSONRPCMessage) -> None:
        root = message
        if isinstance(root, types.JSONRPCRequest):
            key = (type(root.id), root.id)
            if key in self.pending or key in self.seen:
                raise WireFailure("duplicate_request_id")
            self.pending.add(key)

    def feed(self, chunk: bytes) -> list[SessionMessage]:
        self.stdout_bytes += len(chunk)
        if self.stdout_bytes > STDOUT_LIMIT:
            raise WireFailure("stdout_limit_exceeded")
        self.buffer.extend(chunk)
        messages = []
        while b"\n" in self.buffer:
            index = self.buffer.index(10)
            if index > FRAME_LIMIT:
                raise WireFailure("frame_limit_exceeded")
            frame = bytes(self.buffer[:index])
            del self.buffer[: index + 1]
            try:
                parsed = jsonrpc_message_adapter.validate_python(
                    parse_json_bytes(frame), by_name=False
                )
            except (ValueError, RecursionError):
                raise WireFailure("invalid_wire_frame") from None
            root = parsed
            if isinstance(root, (types.JSONRPCResponse, types.JSONRPCError)):
                key = (type(root.id), root.id)
                if key in self.seen:
                    raise WireFailure("duplicate_response_id")
                if key not in self.pending:
                    raise WireFailure("unmatched_response_id")
                self.pending.remove(key)
                self.seen.add(key)
            elif isinstance(root, types.JSONRPCRequest):
                raise WireFailure("server_request_unsupported")
            self.frames += 1
            if self.frames > 1024:
                raise WireFailure("frame_count_exceeded")
            messages.append(SessionMessage(parsed))
        if len(self.buffer) > FRAME_LIMIT:
            raise WireFailure("frame_limit_exceeded")
        return messages

    def stderr(self, chunk: bytes) -> None:
        self.stderr_bytes += len(chunk)
        if self.stderr_bytes > STDERR_LIMIT:
            raise WireFailure("stderr_limit_exceeded")


@asynccontextmanager
async def bounded_transport(process: Process, state: WireState) -> AsyncIterator[Streams]:
    incoming, read = anyio.create_memory_object_stream[SessionMessage | Exception](16)
    write, outgoing = anyio.create_memory_object_stream[SessionMessage](16)

    async def fail(code: str) -> None:
        state.fail(code)
        # Closing the input wakes SDK response waiters; no untrusted exception escapes.
        await incoming.aclose()

    async def stdout() -> None:
        assert process.stdout is not None
        try:
            while True:
                chunk = await process.stdout.receive(4096)
                if state.error:
                    continue  # Discard without decoding; keep Docker attach unblocked for rm.
                try:
                    messages = state.feed(chunk)
                except WireFailure as error:
                    await fail(str(error))
                    continue
                for message in messages:
                    try:
                        incoming.send_nowait(message)
                    except anyio.BrokenResourceError:
                        pass  # Still validate trailing frames after SDK session closes.
                    except anyio.WouldBlock:
                        await fail("inbound_backpressure")
                        break  # Remain in the raw discard loop until container cleanup.
        except anyio.EndOfStream:
            if state.buffer:
                await fail("truncated_wire_frame")
            await incoming.aclose()
        except WireFailure as error:
            await fail(str(error))
        except (OSError, anyio.ClosedResourceError, anyio.BrokenResourceError):
            await fail("stdout_interrupted")

    async def stderr() -> None:
        assert process.stderr is not None
        try:
            while True:
                chunk = await process.stderr.receive(4096)
                if state.error:
                    continue
                try:
                    state.stderr(chunk)
                except WireFailure as error:
                    await fail(str(error))
        except anyio.EndOfStream:
            return
        except WireFailure as error:
            await fail(str(error))
        except (OSError, anyio.ClosedResourceError, anyio.BrokenResourceError):
            await fail("stderr_interrupted")

    async def stdin() -> None:
        assert process.stdin is not None
        try:
            async with outgoing:
                async for message in outgoing:
                    state.request(message.message)
                    data = message.message.model_dump_json(by_alias=True, exclude_unset=True)
                    await process.stdin.send((data + "\n").encode())
        except WireFailure as error:
            await fail(str(error))
        except (OSError, anyio.ClosedResourceError, anyio.BrokenResourceError):
            await fail("stdin_interrupted")

    async with anyio.create_task_group() as group:
        group.start_soon(stdout)
        group.start_soon(stderr)
        group.start_soon(stdin)
        try:
            yield read, write
        finally:
            group.cancel_scope.cancel()
    await read.aclose()
    await write.aclose()
