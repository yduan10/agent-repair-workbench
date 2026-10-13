import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_workbench import api
from agent_workbench.checker import MAX_BYTES, check_bytes
from agent_workbench.models import Report


@pytest.fixture
def client():
    with TestClient(api.create_app(), base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.mark.parametrize("case", ["pass", "fail", "missing", "precision", "duplicate"])
def test_http_matches_checker(client, evidence, case):
    if case == "fail":
        evidence["result"]["structured_content"] = {"count": "SECRET"}
    if case == "missing":
        del evidence["result"]
    raw = json.dumps(evidence).encode()
    if case == "precision":
        raw = raw.replace(b'"id": 1', b'"id": 9007199254740993.0')
    if case == "duplicate":
        raw = raw.replace(b'"id": 1', b'"id": 1, "id": 2')
    response = client.post("/api/check", content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert response.json() == check_bytes(raw).model_dump()
    assert "SECRET" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({"content-type": "text/plain"}, 415, "unsupported_media_type"),
        (
            {"content-type": "application/json", "origin": "https://evil.test"},
            403,
            "origin_forbidden",
        ),
        (
            {"content-type": "application/json", "sec-fetch-site": "cross-site"},
            403,
            "origin_forbidden",
        ),
    ],
)
def test_http_browser_boundary(client, headers, status, code):
    response = client.post("/api/check", content=b"{}", headers=headers)
    assert response.status_code == status
    assert response.json() == {"error": code}


def test_host_and_body_boundaries(client):
    forbidden = client.get("/api/health", headers={"host": "evil.test"})
    assert forbidden.status_code == 400
    assert forbidden.json() == {"error": "host_forbidden"}
    assert forbidden.headers["cache-control"] == "no-store"
    response = client.post(
        "/api/check", content=b" " * (MAX_BYTES + 1), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"error": "input_limit_exceeded"}


def test_busy_does_not_block_health_or_spawn_again(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def slow(raw, timeout):
        entered.set()
        assert release.wait(5)
        return Report()

    monkeypatch.setattr(api, "run_check", slow)
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(
            client.post, "/api/check", content=b"{}", headers={"content-type": "application/json"}
        )
        try:
            assert entered.wait(3)
            assert client.get("/api/health").status_code == 200
            response = client.post(
                "/api/check", content=b"{}", headers={"content-type": "application/json"}
            )
            assert response.status_code == 429
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 200


def test_server_errors_do_not_leak(client, monkeypatch):
    def fail(raw, timeout):
        raise RuntimeError("SENSITIVE_ERROR")

    monkeypatch.setattr(api, "run_check", fail)
    response = client.post(
        "/api/check", content=b"{}", headers={"content-type": "application/json"}
    )
    assert response.status_code == 503
    assert response.json() == {"error": "checker_unavailable"}


@pytest.mark.parametrize("worker_fails", [False, True])
def test_cancelled_http_holds_slot_until_worker_finishes(monkeypatch, worker_fails):
    entered, release = threading.Event(), threading.Event()

    def slow(raw, timeout):
        entered.set()
        assert release.wait(5)
        if worker_fails:
            raise RuntimeError("private worker failure")
        return Report()

    monkeypatch.setattr(api, "run_check", slow)

    async def scenario():
        app = api.create_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://127.0.0.1"
            ) as client:
                task = asyncio.create_task(
                    client.post(
                        "/api/check", content=b"{}", headers={"content-type": "application/json"}
                    )
                )
                assert await asyncio.to_thread(entered.wait, 3)
                task.cancel()
                try:
                    await asyncio.sleep(0.02)
                    assert app.state.gate.locked()
                    task.cancel()
                    response = await client.post(
                        "/api/check", content=b"{}", headers={"content-type": "application/json"}
                    )
                    assert response.status_code == 429
                finally:
                    release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
                await asyncio.wait_for(asyncio.gather(*app.state.workers), timeout=3)
                assert not app.state.gate.locked()
                response = await client.post(
                    "/api/check", content=b"{}", headers={"content-type": "application/json"}
                )
                assert response.status_code == (503 if worker_fails else 200)

    asyncio.run(scenario())
