"""Independent repair gateway checks; local resources and mock HTTP only."""

import asyncio
import json

import httpx
import pytest

from agent_workbench.model_gateway.gateway import PROFILE, Config, GatewayError
from agent_workbench.model_gateway.repair import ROLES, RepairDeepSeekAdapter


def config():
    return Config("https://example.invalid", "deepseek-flash", "private-test-key", PROFILE)


@pytest.mark.parametrize("failure", [b"", b"\xff", b"x" * 8193, OSError("private/path secret")])
def test_prompt_read_failure_is_static_and_has_no_sensitive_exception(monkeypatch, failure):
    import agent_workbench.model_gateway.repair as module

    class Resource:
        def joinpath(self, name):
            return self

        def read_bytes(self):
            if isinstance(failure, OSError):
                raise failure
            return failure

    monkeypatch.setattr(module, "files", lambda package: Resource())
    with pytest.raises(GatewayError) as caught:
        RepairDeepSeekAdapter(config())
    assert str(caught.value) == "MODEL_CONFIGURATION_INVALID"
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("changed_role", ROLES)
def test_each_prompt_versions_all_modes_but_existing_adapter_remains_frozen(
    monkeypatch, changed_role
):
    import agent_workbench.model_gateway.repair as module

    before = RepairDeepSeekAdapter(config())
    original = {role: before.prompt(role) for role in ROLES}

    class Resource:
        def __init__(self, package):
            self.role = package.rsplit(".", 1)[-1]

        def joinpath(self, name):
            return self

        def read_bytes(self):
            return (
                original[self.role] + ("\nrevision" if self.role == changed_role else "")
            ).encode()

    monkeypatch.setattr(module, "files", Resource)
    after = RepairDeepSeekAdapter(config())
    assert before.config_sha256 != after.config_sha256
    for role in ROLES:
        assert before.prompt(role) == original[role]
        assert (
            before.prepare(role, [], 8192).reservation_sha256
            != after.prepare(role, [], 8192).reservation_sha256
        )
    assert before.prepare(changed_role, [], 8192) == before.prepare(changed_role, [], 8192)


@pytest.mark.parametrize("changed_role", ROLES)
def test_every_schema_changes_shared_fingerprint(monkeypatch, changed_role):
    import agent_workbench.model_gateway.repair as module

    before = RepairDeepSeekAdapter(config())
    adapter = getattr(module, changed_role.upper() + "_ADAPTER")
    schema = adapter.json_schema()
    monkeypatch.setattr(adapter, "json_schema", lambda: {**schema, "title": "new revision"})
    after = RepairDeepSeekAdapter(config())
    assert before.config_sha256 != after.config_sha256
    assert (
        before.prepare("single", [], 8192).reservation_sha256
        != after.prepare("single", [], 8192).reservation_sha256
    )


@pytest.mark.parametrize(
    "kind,error",
    [
        ("status", "MODEL_TRANSPORT_ERROR"),
        ("oversized", "MODEL_RESPONSE_INVALID"),
        ("no_usage", "MODEL_USAGE_UNKNOWN"),
        ("exception", "MODEL_TRANSPORT_ERROR"),
    ],
)
def test_shared_sender_bounds_untrusted_reply_and_retains_unknown_usage(kind, error):
    async def handler(request):
        assert json.loads(request.content)["max_tokens"] == 8192
        if kind == "status":
            return httpx.Response(500, content=b"private-response")
        if kind == "oversized":
            return httpx.Response(200, content=b"private-response" * 10000)
        if kind == "no_usage":
            return httpx.Response(200, json={"content": "private-response"})
        raise httpx.ReadError("private-response", request=request)

    adapter = RepairDeepSeekAdapter(config(), transport=httpx.MockTransport(handler))
    reply = asyncio.run(adapter.send(adapter.prepare("single", [], 8192), 1))
    assert reply.error == error and not reply.usage_known and reply.decision is None
    assert "private" not in repr(reply)
