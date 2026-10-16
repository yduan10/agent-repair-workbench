"""Opt-in browser -> production Next proxy -> real API/SQLite; only model/Docker are fake."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tests.agents.test_repair_tool_bridge import ctx as ctx

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.getenv("AWB_B3_BROWSER") != "1", reason="explicit isolated browser gate")
def test_browser_live(ctx, tmp_path):
    for port in (8030, 3015):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    calls = tmp_path / "calls.jsonl"
    env = {
        **os.environ,
        "AWB_STATE_DIR": str(ctx.store.directory),
        "B2_TEST_IMAGE": str(ctx.image),
        "B2_TEST_CALLS": str(calls),
        "AWB_FRONTEND_PORT": "3015",
        "PYTHONPATH": str(ROOT),
        "AWB_API_PORT": "8030",
        "PW_PORT": "3015",
        "PLAYWRIGHT_CHANNEL": "chrome",
    }
    with (tmp_path / "api.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "tests.web_repair_http_fixture:factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8030",
                "--no-access-log",
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    if httpx.get("http://127.0.0.1:8030/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline and server.poll() is None
                time.sleep(0.1)
            result = subprocess.run(
                ["npx", "playwright", "test", "tests/b3-browser-live.spec.ts"],
                cwd=ROOT / "frontend",
                env=env,
                capture_output=True,
                text=True,
                timeout=100,
            )
            (ROOT / "artifacts/b3-browser-live.log").write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stdout + result.stderr
            rows = [json.loads(line) for line in calls.read_text().splitlines()]
            assert len(rows) == 1
        finally:
            server.terminate()
            try:
                server.wait(15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(5)
