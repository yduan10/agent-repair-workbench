"""Actual TCP/Uvicorn workers, disconnect, SIGSTOP and graceful shutdown on isolated state."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from agent_workbench.web_repairs.store import WebRepairStore
from tests.agents.test_repair_tool_bridge import ctx as ctx

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX worker ownership")
ROOT = Path(__file__).resolve().parents[1]
ORIGIN = {"origin": "http://127.0.0.1:3010"}


def eventually(fn, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            value = fn()
            if value:
                return value
        except (httpx.HTTPError, ConnectionError, OSError):
            pass
        time.sleep(0.05)
    raise AssertionError("bounded worker wait expired")


def payload():
    return {"request_id": str(uuid4()), "case_id": "counter_offset", "mode": "three_role"}


def test_two_http_workers_disconnect_stop_and_shutdown(ctx, tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    calls_path = tmp_path / "calls.jsonl"
    env = {
        **os.environ,
        "AWB_STATE_DIR": str(ctx.store.directory),
        "B2_TEST_IMAGE": str(ctx.image),
        "B2_TEST_CALLS": str(calls_path),
        "AWB_FRONTEND_PORT": "3010",
        "PYTHONPATH": str(ROOT),
    }
    clients, workers = [], {}
    stopped_pid = None
    store = WebRepairStore(ctx.store.directory)
    with (tmp_path / "server.log").open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.web_repair_http_fixture:factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                "2",
                "--log-level",
                "warning",
                "--no-access-log",
            ],
            env=env,
            cwd=ROOT,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

        def calls():
            return (
                [json.loads(line) for line in calls_path.read_text().splitlines()]
                if calls_path.exists()
                else []
            )

        def connection():
            client = httpx.Client(base_url=url, timeout=2, headers=ORIGIN)
            clients.append(client)
            pid = client.get("/api/test-worker").json()["pid"]
            workers[pid] = client
            return len(workers) == 2

        try:
            eventually(connection, 20)
            first, second = list(workers.values())
            data = payload()
            with ThreadPoolExecutor(2) as pool:
                a = pool.submit(first.post, "/api/repair-runs", json=data)
                b = pool.submit(second.post, "/api/repair-runs", json=data)
                statuses = [a.result().status_code, b.result().status_code]
            assert statuses.count(202) == 1 and all(s in (200, 202, 429) for s in statuses)
            eventually(lambda: len(calls()) == 1)
            assert first.post("/api/repair-runs", json=data).status_code == 200
            assert second.post("/api/repair-runs", json=payload()).status_code == 429
            assert (
                first.post(f"/api/repair-runs/{data['request_id']}/cancel", json={}).status_code
                == 202
            )
            eventually(lambda: not store.receipt(data["request_id"]).active)
            # Submit raw HTTP and drop the connection before reading its response.
            lost = payload()
            raw = json.dumps(lost).encode()
            with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
                sock.sendall(
                    (
                        f"POST /api/repair-runs HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                        "Origin: http://127.0.0.1:3010\r\nContent-Type: application/json\r\n"
                        f"Content-Length: {len(raw)}\r\nConnection: close\r\n\r\n"
                    ).encode()
                    + raw
                )
            eventually(lambda: len(calls()) == 2)
            owner_pid = calls()[-1]["pid"]
            healthy = next(client for pid, client in workers.items() if pid != owner_pid)
            assert healthy.post("/api/repair-runs", json=lost).status_code == 200
            os.kill(owner_pid, signal.SIGSTOP)
            stopped_pid = owner_pid
            assert healthy.get("/api/repair-runs/catalog").json()["slot"]["status"] == "busy"
            assert healthy.post("/api/repair-runs", json=payload()).status_code == 429
            assert len(calls()) == 2
            os.kill(owner_pid, signal.SIGCONT)
            stopped_pid = None
            assert (
                healthy.post(f"/api/repair-runs/{lost['request_id']}/cancel", json={}).status_code
                == 202
            )
            eventually(lambda: not store.receipt(lost["request_id"]).active)
            third = payload()
            assert healthy.post("/api/repair-runs", json=third).status_code == 202
            eventually(lambda: len(calls()) == 3)
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=20)
            saved = store.receipt(third["request_id"])
            assert saved.cancel_requested and saved.saved.task.phase == "finished"
            assert saved.saved.task.usage.reserved_tokens > 0
            assert len(calls()) == 3 and len({c["task_id"] for c in calls()}) == 3
        finally:
            if stopped_pid:
                os.kill(stopped_pid, signal.SIGCONT)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            for client in clients:
                client.close()
            store.close()
