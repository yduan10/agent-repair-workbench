import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_workbench.checker import MAX_BYTES, check_bytes, pointer


def check(document):
    return check_bytes(json.dumps(document).encode())


def codes(report):
    return [finding.code for finding in report.findings]


def test_valid_and_stable_digest(evidence):
    report = check(evidence)
    reordered = json.dumps(evidence, sort_keys=True, indent=4).encode()
    assert report.status == "passed"
    assert report.checks.input == report.checks.output == "passed"
    assert not report.findings
    assert report == check_bytes(reordered)
    evidence["call"]["arguments"]["id"] = 2
    assert check(evidence).evidence_sha256 != report.evidence_sha256


def test_reordered_invalid_evidence_has_identical_report(evidence):
    evidence["tool"]["input_schema"] = {
        "type": "object",
        "properties": {"z": {"type": "integer"}, "a": {"type": "integer"}},
    }
    evidence["call"]["arguments"] = {"z": "wrong", "a": "wrong"}
    report = check(evidence)
    assert report.status == "failed"
    assert report == check_bytes(json.dumps(evidence, sort_keys=True).encode())


@pytest.mark.parametrize("arguments", [{}, {"id": "1"}, {"id": True}, {"id": 1, "x": 2}])
def test_argument_failures(evidence, arguments):
    evidence["call"]["arguments"] = arguments
    report = check(evidence)
    assert report.status == "failed"
    assert report.checks.input == "failed"
    assert "input_schema_violation" in codes(report)


def test_nested_array_pointer(evidence):
    evidence["tool"]["input_schema"] = {
        "type": "object",
        "properties": {"a/~": {"type": "array", "items": {"type": "integer"}}},
    }
    evidence["call"]["arguments"] = {"a/~": [1, "sensitive-secret"]}
    report = check(evidence)
    assert report.findings[0].instance_path == "/call/arguments/a~1~0/1"
    assert report.findings[0].schema_path == "/properties/a~1~0/items/type"
    assert "sensitive-secret" not in report.model_dump_json()


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"is_error": True}, "tool_error"),
        ({"call_id": "other"}, "result_call_mismatch"),
        ({"structured_content": {"count": "secret-value"}}, "output_schema_violation"),
        ({"structured_content": None}, "output_schema_violation"),
    ],
)
def test_result_failures(evidence, change, expected):
    evidence["result"].update(change)
    report = check(evidence)
    assert report.status == "failed"
    assert expected in codes(report)
    assert "secret-value" not in report.model_dump_json()


def test_missing_result_and_failure_precedence(evidence):
    del evidence["result"]
    report = check(evidence)
    assert report.status == "inconclusive"
    assert codes(report) == ["result_missing"]
    evidence["call"]["arguments"] = {}
    assert check(evidence).status == "failed"


def test_tool_name_mismatch(evidence):
    evidence["call"]["tool_name"] = "other"
    assert check(evidence).status == "failed"
    assert "tool_name_mismatch" in codes(check(evidence))


def test_no_output_schema_not_checked(evidence):
    del evidence["tool"]["output_schema"]
    del evidence["result"]["structured_content"]
    report = check(evidence)
    assert report.status == "passed"
    assert report.checks.output == "not_checked"


def test_missing_structured_result(evidence):
    del evidence["result"]["structured_content"]
    report = check(evidence)
    assert report.status == "failed"
    assert "structured_content_missing" in codes(report)


@pytest.mark.parametrize("key", ["$ref", "$dynamicRef", "$id", "format", "pattern", "x-assert"])
def test_unsupported_schema_never_passes(evidence, key):
    evidence["tool"]["input_schema"][key] = "https://example.invalid/secret"
    report = check(evidence)
    assert report.status == "inconclusive"
    assert codes(report) == ["unsupported_schema"]
    assert "secret" not in report.model_dump_json()


@pytest.mark.parametrize("schema", [{"type": "object", "required": 1}, {"type": "invalid"}])
def test_invalid_schema(evidence, schema):
    evidence["tool"]["input_schema"] = schema
    report = check(evidence)
    assert report.status == "inconclusive"
    assert "invalid_schema" in codes(report)


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {"id": {"$ref": "#/somewhere"}}},
        {"type": "object", "allOf": [{"format": "email"}]},
        {"type": "array"},
        {"type": "object", "$schema": "http://json-schema.org/draft-07/schema#"},
    ],
)
def test_nested_or_wrong_draft_unsupported(evidence, schema):
    evidence["tool"]["input_schema"] = schema
    assert codes(check(evidence)) == ["unsupported_schema"]


def test_schema_data_is_not_schema(evidence):
    evidence["tool"]["input_schema"] = {
        "type": "object",
        "properties": {"$ref": {"const": {"$ref": "literal-data"}}},
        "examples": [{"pattern": "data"}],
        "default": {"$ref": "data"},
    }
    evidence["call"]["arguments"] = {"$ref": {"$ref": "literal-data"}}
    assert check(evidence).status == "passed"


@pytest.mark.parametrize("version", [True, "1", 1.0, 2, None])
def test_strict_version(evidence, version):
    evidence["schema_version"] = version
    assert codes(check(evidence)) == ["invalid_document"]


@pytest.mark.parametrize("target", ["root", "call", "result", "tool"])
def test_unknown_envelope_fields(evidence, target):
    destination = evidence if target == "root" else evidence[target]
    destination["secret-field"] = "secret-value"
    report = check(evidence)
    assert report.status == "inconclusive"
    assert "secret" not in report.model_dump_json()


@pytest.mark.parametrize("target", ["output_schema", "result"])
def test_explicit_null_rejected(evidence, target):
    if target == "result":
        evidence["result"] = None
    else:
        evidence["tool"][target] = None
    assert codes(check(evidence)) == ["invalid_document"]


@pytest.mark.parametrize(
    "raw",
    [b'{"x": 1, "x": 2}', b"NaN", b"Infinity", b"-Infinity", b"\xff", b"{", b'"\\ud800"'],
)
def test_invalid_json(raw):
    report = check_bytes(raw)
    assert report.status == "inconclusive"
    assert codes(report) == ["invalid_document"]


@pytest.mark.parametrize(
    ("value", "divisor", "status"),
    [
        (0.3, 0.1, "passed"),
        (0.07, 0.01, "passed"),
        (0.30000000000000004, 0.1, "failed"),
        (0.31, 0.1, "failed"),
    ],
)
def test_exact_decimal_multiple_of(evidence, value, divisor, status):
    evidence["tool"]["input_schema"]["properties"]["id"] = {"type": "number", "multipleOf": divisor}
    evidence["call"]["arguments"]["id"] = value
    assert check(evidence).status == status


@pytest.mark.parametrize("literal", ["1e-999", "1e999", "9007199254740993.0", "1e23"])
def test_precision_loss_is_inconclusive(evidence, literal):
    evidence["tool"]["input_schema"]["properties"]["id"] = {"const": 0}
    evidence["call"]["arguments"]["id"] = "REPLACE_NUMBER"
    raw = json.dumps(evidence).replace('"REPLACE_NUMBER"', literal).encode()
    report = check_bytes(raw)
    assert report.status == "inconclusive"
    assert codes(report) == ["unsupported_number"]


def test_large_integer_decimal_cannot_round_into_const(evidence):
    evidence["tool"]["input_schema"]["properties"]["id"] = {"const": 9007199254740992}
    evidence["call"]["arguments"]["id"] = "REPLACE_NUMBER"
    raw = json.dumps(evidence).replace('"REPLACE_NUMBER"', "9007199254740993.0").encode()
    assert check_bytes(raw).status == "inconclusive"


@pytest.mark.parametrize(
    ("constraint", "value", "status"),
    [
        ({"minimum": 9007199254740992}, 9007199254740992.0, "passed"),
        ({"exclusiveMinimum": 9007199254740992}, 9007199254740992.0, "failed"),
        ({"const": 9007199254740992}, 9007199254740992.0, "passed"),
        ({"enum": [9007199254740992]}, 9007199254740992.0, "passed"),
        ({"type": "array", "uniqueItems": True}, [9007199254740992, 9007199254740992.0], "failed"),
        ({"type": "number", "multipleOf": 0.1}, True, "failed"),
    ],
)
def test_numeric_keyword_boundaries(evidence, constraint, value, status):
    evidence["tool"]["input_schema"]["properties"]["id"] = constraint
    evidence["call"]["arguments"]["id"] = value
    assert check(evidence).status == status


def test_schema_number_precision_also_rejected(evidence):
    evidence["tool"]["input_schema"]["properties"]["id"] = {"const": "REPLACE_NUMBER"}
    raw = json.dumps(evidence).replace('"REPLACE_NUMBER"', "1e-999").encode()
    assert codes(check_bytes(raw)) == ["unsupported_number"]


def test_nested_dialect_keeps_exact_numeric_validation(evidence):
    evidence["tool"]["input_schema"]["properties"]["id"] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "number",
        "multipleOf": 0.1,
    }
    evidence["call"]["arguments"]["id"] = 0.3
    assert check(evidence).status == "passed"


def test_input_limits():
    assert codes(check_bytes(b" " * (MAX_BYTES + 1))) == ["input_limit_exceeded"]
    assert codes(check_bytes(b"[" * 34 + b"0" + b"]" * 34)) == ["input_limit_exceeded"]
    assert codes(check_bytes(json.dumps([0] * 20_001).encode())) == ["input_limit_exceeded"]


def test_findings_truncated_still_failed(evidence):
    evidence["tool"]["input_schema"] = {
        "type": "object",
        "required": [f"missing{i}" for i in range(60)],
    }
    evidence["result"]["is_error"] = True
    report = check(evidence)
    assert report.status == "failed"
    assert len(report.findings) == 50
    assert report.findings_truncated


def test_boolean_subschema(evidence):
    evidence["tool"]["input_schema"] = {"type": "object", "properties": {"id": False}}
    assert check(evidence).status == "failed"


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80))
def test_pointer_roundtrip(key):
    encoded = pointer([key])
    assert encoded.startswith("/")
    assert encoded[1:].replace("~1", "/").replace("~0", "~") == key


@given(st.integers(min_value=-1_000_000, max_value=1_000_000))
def test_integer_boundary_contract(value):
    document = {
        "schema_version": 1,
        "tool": {
            "name": "t",
            "input_schema": {
                "type": "object",
                "properties": {"n": {"type": "integer", "minimum": 0}},
            },
        },
        "call": {"call_id": "c", "tool_name": "t", "arguments": {"n": value}},
        "result": {"call_id": "c", "is_error": False},
    }
    assert check(document).status == ("passed" if value >= 0 else "failed")
