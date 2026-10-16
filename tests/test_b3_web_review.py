"""Independent B3 public event audit tests; temporary SQLite, scripted model only."""

import json

import httpx
import pytest
from sqlalchemy import delete, select, update

from agent_workbench import api
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.run_store.schema import repair_events
from agent_workbench.web_repairs.models import RepairRequest
from agent_workbench.web_repairs.store import WebRepairStore
from tests.agents.test_repair_tool_bridge import ctx as ctx
from tests.test_web_repair_api import anyio_backend as anyio_backend
from tests.test_web_repair_api import drained, request
from tests.test_web_repair_api import host as host


@pytest.mark.anyio
async def test_events_are_whitelisted_complete_and_read_only(host):
    service, model = host
    data = request()
    assert (await service.submit(RepairRequest(**data))).status == 202
    await drained(service)
    result = await service.events(data["request_id"])
    assert result.status == 200
    body = result.body
    assert set(body) == {"schema_version", "task_id", "revision", "events"}
    assert len(body["events"]) == body["revision"] + 1
    assert body["events"][0]["kind"] == "created"
    assert body["events"][-1]["kind"] == "finished"
    assert [e["revision"] for e in body["events"]] == list(range(body["revision"] + 1))
    for event in body["events"]:
        assert set(event) == {
            "revision",
            "at",
            "kind",
            "role",
            "operation",
            "tool",
            "status",
            "error_code",
        }
    before = await service.read(data["request_id"])
    assert (await service.events(data["request_id"])).body == body
    after = await service.read(data["request_id"])
    assert before.body == after.body and model.calls == 1
    text = json.dumps(body)
    assert str(service.directory) not in text
    assert not any(
        k in text for k in ("claim", "request_sha256", "reservation_sha256", "payload_sha256")
    )
    await service.close()


@pytest.mark.parametrize("mutation", ["missing", "hash", "semantic"])
@pytest.mark.anyio
async def test_public_events_reject_corruption_even_when_payload_hash_is_recomputed(host, mutation):
    service, _ = host
    data = request()
    await service.submit(RepairRequest(**data))
    await drained(service)
    store = WebRepairStore(service.directory)
    try:
        with store._base._transaction(write=True) as connection:
            where = (repair_events.c.task_id == data["request_id"]) & (
                repair_events.c.revision == 1
            )
            row = connection.execute(select(repair_events).where(where)).mappings().one()
            if mutation == "missing":
                connection.execute(delete(repair_events).where(where))
            elif mutation == "hash":
                connection.execute(update(repair_events).where(where).values(sha256="0" * 64))
            else:
                payload = json.loads(row["payload"])
                payload["request"]["role"] = "single"
                raw = canonical(payload)
                connection.execute(
                    update(repair_events).where(where).values(payload=raw, sha256=digest(raw))
                )
        result = await service.events(data["request_id"])
        assert result.status == 503 and result.body == {"error": "store_unavailable"}
    finally:
        store.close()
        await service.close()


@pytest.mark.anyio
async def test_events_share_reader_capacity_and_release_after_read(host):
    service, _ = host
    data = request()
    await service.submit(RepairRequest(**data))
    await drained(service)
    await service.reads.acquire()
    await service.reads.acquire()
    try:
        assert (await service.events(data["request_id"])).body == {"error": "repair_reads_busy"}
    finally:
        service.reads.release()
        service.reads.release()
    assert (await service.events(data["request_id"])).status == 200
    assert not service.reads.locked()
    await service.close()


@pytest.mark.anyio
async def test_event_http_rejects_extra_query_bad_id_and_unknown_web_task(host):
    service, _ = host
    app = api.create_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://127.0.0.1"
        ) as client,
    ):
        task_id = request()["request_id"]
        for path, expected in (
            ("bad/events", 400),
            (task_id + "/events?limit=1", 400),
            (task_id + "/events", 404),
        ):
            result = await client.get("/api/repair-runs/" + path)
            assert result.status_code == expected
            assert result.headers["cache-control"] == "no-store"
    assert not service.tasks
