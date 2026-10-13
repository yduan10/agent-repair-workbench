"""Independent review regression: backpressure must not stop raw pipe drainage."""

from types import SimpleNamespace

import anyio
import pytest

from agent_workbench.runner.transport import WireState, bounded_transport


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Pipe:
    def __init__(self, receiver):
        self.receiver = receiver
        self.reads = 0

    async def receive(self, maximum=4096):
        self.reads += 1
        return await self.receiver.receive()

    async def send(self, data):
        pass


@pytest.mark.anyio
async def test_backpressure_failure_keeps_draining_until_cleanup():
    sender, receiver = anyio.create_memory_object_stream(1)
    errors, error_receiver = anyio.create_memory_object_stream(1)
    output = Pipe(receiver)
    process = SimpleNamespace(stdout=output, stderr=Pipe(error_receiver), stdin=Pipe(None))
    state = WireState()
    frame = (
        b'{"jsonrpc":"2.0","method":"notifications/message",'
        b'"params":{"level":"info","data":"synthetic"}}\n'
    )
    try:
        async with bounded_transport(process, state):
            # Leave the SDK reader unconsumed: its 16-slot buffer must fill.
            with anyio.fail_after(1):
                for _ in range(17):
                    await sender.send(frame)
                while state.error is None:
                    await anyio.sleep(0.001)
            assert state.error == "inbound_backpressure"
            # A real stdout producer must still progress after rejection so Docker
            # attach and rm can terminate; a reader exiting on WouldBlock fails here.
            with anyio.fail_after(1):
                for _ in range(100):
                    await sender.send(frame)
            assert state.error == "inbound_backpressure"
            assert output.reads >= 117
    finally:
        await sender.aclose()
        await errors.aclose()
        await receiver.aclose()
        await error_receiver.aclose()
