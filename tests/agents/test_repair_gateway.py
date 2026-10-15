"""P0-06 protocol checks use local mock HTTP, never a real model or credentials."""

import asyncio
import copy
import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from agent_workbench.model_gateway.gateway import (
    INPUT_BOUND,
    PROFILE,
    Config,
    DeepSeekAdapter,
    GatewayError,
    prepare_decision_call,
)
from agent_workbench.model_gateway.repair import ROLES, RepairDeepSeekAdapter
from agent_workbench.repair_contracts.codec import decode_role


def config(key="test-only"):
    return Config("https://example.invalid", "deepseek-flash", key, PROFILE)


def test_p005_wire_format_and_accounting_fingerprint_unchanged():
    old = DeepSeekAdapter(config())
    assert old.config_sha256 == "1a7ae053995f586ce38560a332ded183cf0a2da61ee84ad5559674ca4b4c4a4f"
    expected = {
        "diagnosis": "4dac9f8af92a0d31d8a46589ca9d12b41a55cfa740359ab3d61853223731a216",
        "repair": "bf02097205e873f4ac73cdad406b24d284ed50fcefecc66d107ac4bdba5f9971",
        "verification": "a85de02ba743f4be975da44df7112c0c08dc7e6527ef19bca071bcf9d0ce02af",
    }
    for role, sha in expected.items():
        prepared = old.prepare(role, [{"role": "user", "content": "compatibility fixture"}], 8192)
        assert prepared.request_sha256 == sha
        reservation = (
            "166e6c48239c597b145c93b2fe8739e53767ff317ecf14beb1084e25cd2c3b00"
            if role == "repair"
            else "ee9971750ad7e3d1e38f2e3a4329340a15c99abc5365e20d9faaeb337735ec1b"
        )
        assert prepared.reservation_sha256 == reservation


def test_shared_builder_keeps_schema_definitions_for_later_requests():
    schema = {"$defs": {"S": {"type": "string"}}, "$ref": "#/$defs/S"}
    before = copy.deepcopy(schema)
    args = (config(), "a" * 64, schema, [], 8192, 8192)
    first = prepare_decision_call(*args)
    assert first == prepare_decision_call(*args)
    assert schema == before
    params = json.loads(first.body)["tools"][0]["function"]["parameters"]
    Draft202012Validator(params).validate({"decision": "value"})


def test_single_and_multi_roles_share_budget_and_resolve_schema_refs():
    adapter = RepairDeepSeekAdapter(config())
    reservations = set()
    for role in ROLES:
        prepared = adapter.prepare(
            role, [{"role": "system", "content": adapter.prompt(role)}], 8192
        )
        assert prepared.input_reserved == INPUT_BOUND
        assert prepared.output_reserved == 8192
        reservations.add(prepared.reservation_sha256)
        body = json.loads(prepared.body)
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 8192
        params = body["tools"][0]["function"]["parameters"]
        Draft202012Validator.check_schema(params)
        conclusion = {
            "schema_version": 1,
            "action": "conclude",
            "disposition": "needs_evidence",
            "reason_code": "evidence_missing",
            "evidence_refs": [],
        }
        Draft202012Validator(params).validate({"decision": conclusion})
        assert decode_role(json.dumps(conclusion).encode(), role).action == "conclude"
    assert len(reservations) == 1
    assert adapter.config_sha256 != DeepSeekAdapter(config()).config_sha256
    assert adapter.config_sha256 == RepairDeepSeekAdapter(config("another-key")).config_sha256
    assert adapter.prepare("single", [], 100).output_reserved == 100


@pytest.mark.parametrize("cap", [0, -1, 32769, True, 1.5])
def test_invalid_cap_is_rejected(cap):
    with pytest.raises(GatewayError, match="BUDGET_EXCEEDED"):
        RepairDeepSeekAdapter(config()).prepare("single", [], cap)


def test_prompt_or_schema_change_versions_configuration(monkeypatch):
    import agent_workbench.model_gateway.repair as module

    original = RepairDeepSeekAdapter(config()).config_sha256
    monkeypatch.setattr(module, "OUTPUT_LIMIT", 4096)
    assert RepairDeepSeekAdapter(config()).config_sha256 != original
    monkeypatch.setattr(module, "OUTPUT_LIMIT", 8192)
    real = module.SINGLE_ADAPTER.json_schema
    monkeypatch.setattr(
        module.SINGLE_ADAPTER, "json_schema", lambda: {**real(), "title": "revision"}
    )
    assert RepairDeepSeekAdapter(config()).config_sha256 != original


def test_repair_transport_preserves_truncation_usage_and_does_not_leak_text():
    async def handler(request):
        assert json.loads(request.content)["max_tokens"] == 8192
        return httpx.Response(
            200,
            json={
                "usage": {"prompt_tokens": 100, "completion_tokens": 8192, "total_tokens": 8292},
                "choices": [{"finish_reason": "length", "message": {"content": "SENSITIVE"}}],
            },
        )

    adapter = RepairDeepSeekAdapter(config(), transport=httpx.MockTransport(handler))
    reply = asyncio.run(adapter.send(adapter.prepare("single", [], 8192), 1))
    assert reply.usage_known and reply.error == "MODEL_OUTPUT_TRUNCATED"
    assert reply.output_tokens == 8192 and "SENSITIVE" not in repr(reply)


def test_cached_schema_not_consumed_by_repeated_prepare():
    adapter = RepairDeepSeekAdapter(config())
    for role in ROLES:
        first = adapter.prepare(role, [], 8192)
        assert adapter.prepare(role, [], 8192) == first
