"""Deterministic offline checks, with deliberately bounded schema support.

The CLI runs this module in a killable process. Callers embedding check_bytes
must provide their own execution deadline: schema complexity is not linear.
"""

import hashlib
import json
import math
from collections.abc import Iterable, Iterator
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from itertools import islice
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.validators import extend
from pydantic import JsonValue
from pydantic import ValidationError as ModelError

from agent_workbench.models import Evidence, Finding, Report, incomplete

MAX_BYTES = 1024 * 1024
MAX_DEPTH = 32
MAX_NODES = 20_000
MAX_FINDINGS = 50
DRAFT = "https://json-schema.org/draft/2020-12/schema"
KEYWORDS = frozenset(
    "$schema title description $comment default examples type properties required "
    "additionalProperties items prefixItems minItems maxItems uniqueItems minProperties "
    "maxProperties minLength maxLength minimum maximum exclusiveMinimum exclusiveMaximum "
    "multipleOf enum const allOf anyOf oneOf not".split()
)


class InputLimitError(ValueError):
    """A configured input resource bound was exceeded."""


class UnsupportedNumberError(ValueError):
    """A JSON number cannot be checked without silently losing precision."""


def pointer(parts: Iterable[str | int]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    parsed = float(value)
    exact = Decimal(value)
    if not math.isfinite(parsed) or exact != Decimal(str(parsed)):
        raise UnsupportedNumberError
    # Cross integer/float comparisons use the binary value, not its decimal text.
    if parsed.is_integer() and exact != Decimal.from_float(parsed):
        raise UnsupportedNumberError
    return parsed


def _multiple_of(
    validator: Draft202012Validator,
    divisor: JsonValue,
    instance: JsonValue,
    schema: dict[str, JsonValue],
) -> Iterator[ValidationError]:
    if not validator.is_type(instance, "number"):
        return
    # Parsing guarantees finite, round-trip-preserving decimals. Rational
    # arithmetic avoids modulo rounding errors and epsilon false passes.
    ratio = Fraction(str(instance)) / Fraction(str(divisor))
    if ratio.denominator != 1:
        yield ValidationError("multipleOf constraint violated")


# jsonschema's public extension factory lacks a typed stub; keep this exception
# localized while using the standard validator interface everywhere else.
ExactMultipleValidator: type[Draft202012Validator] = extend(  # type: ignore[no-untyped-call]
    Draft202012Validator, {"multipleOf": _multiple_of}
)


def _reject_constant(value: str) -> None:
    raise ValueError("non-JSON constant")


def _check_size(value: JsonValue) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise InputLimitError
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _schemas(schema: JsonValue) -> Iterator[tuple[dict[str, JsonValue], list[str | int]]]:
    """Walk only schema positions; instance data and property names are not keywords."""
    pending: list[tuple[JsonValue, list[str | int]]] = [(schema, [])]
    while pending:
        node, path = pending.pop()
        if not isinstance(node, dict):
            continue
        yield node, path
        for key in ("additionalProperties", "items", "not"):
            if key in node:
                pending.append((node[key], [*path, key]))
        properties = node.get("properties")
        if isinstance(properties, dict):
            pending.extend((child, [*path, "properties", k]) for k, child in properties.items())
        for key in ("prefixItems", "allOf", "anyOf", "oneOf"):
            children = node.get(key)
            if isinstance(children, list):
                pending.extend((child, [*path, key, i]) for i, child in enumerate(children))


def _schema_issue(schema: dict[str, JsonValue], phase: str) -> Finding | None:
    for node, path in _schemas(schema):
        for key in node:
            if key not in KEYWORDS or (key == "$schema" and node[key] != DRAFT):
                return Finding(code="unsupported_schema", phase=phase, schema_path=pointer(path))
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        return Finding(code="invalid_schema", phase=phase)
    if schema.get("type") != "object":
        return Finding(code="unsupported_schema", phase=phase)
    return None


def _violations(
    schema: dict[str, JsonValue], value: JsonValue, phase: str, prefix: str
) -> Iterator[Finding]:
    normalized = deepcopy(schema)
    # Already checked against the sole supported dialect. A nested $schema
    # would otherwise make jsonschema.evolve select its default float validator.
    for node, _ in _schemas(normalized):
        node.pop("$schema", None)
    errors: Iterable[ValidationError] = ExactMultipleValidator(normalized).iter_errors(value)
    for error in errors:
        yield Finding(
            code=f"{phase}_schema_violation",
            phase=phase,
            instance_path=prefix + pointer(error.absolute_path),
            schema_path=pointer(error.absolute_schema_path),
        )


def _append(report: Report, findings: Iterable[Finding]) -> bool:
    """Collect a bounded number, while retaining the fact that a failure exists."""
    remaining = MAX_FINDINGS - len(report.findings)
    batch = list(islice(findings, remaining + 1))
    report.findings.extend(batch[:remaining])
    report.findings_truncated |= len(batch) > remaining
    return bool(batch)


def _check(evidence: Evidence, digest: str) -> Report:
    report = Report(evidence_sha256=digest)
    for phase, schema in (
        ("input", evidence.tool.input_schema),
        ("output", evidence.tool.output_schema),
    ):
        if schema is not None and (issue := _schema_issue(schema, phase)):
            report.findings.append(issue)
            return report

    failed = False
    if evidence.call.tool_name != evidence.tool.name:
        _append(report, [Finding(code="tool_name_mismatch", phase="call", instance_path="/call")])
        failed = True
    invalid_input = _append(
        report,
        _violations(
            evidence.tool.input_schema, evidence.call.arguments, "input", "/call/arguments"
        ),
    )
    report.checks.input = "failed" if invalid_input else "passed"
    failed |= invalid_input

    result = evidence.result
    if result is None:
        _append(report, [Finding(code="result_missing", phase="result", instance_path="/result")])
        report.status = "failed" if failed else "inconclusive"
        report.checks.output = "skipped"
        return report
    if result.call_id != evidence.call.call_id:
        _append(
            report, [Finding(code="result_call_mismatch", phase="result", instance_path="/result")]
        )
        failed = True
        report.checks.output = "skipped"
    elif result.is_error:
        _append(report, [Finding(code="tool_error", phase="result", instance_path="/result")])
        failed = True
        report.checks.output = "skipped"
    elif evidence.tool.output_schema is not None:
        if "structured_content" not in result.model_fields_set:
            _append(report, [Finding(code="structured_content_missing", phase="output")])
            failed = True
            report.checks.output = "failed"
        else:
            invalid_output = _append(
                report,
                _violations(
                    evidence.tool.output_schema,
                    result.structured_content,
                    "output",
                    "/result/structured_content",
                ),
            )
            report.checks.output = "failed" if invalid_output else "passed"
            failed |= invalid_output
    report.status = "failed" if failed else "passed"
    return report


def parse_json_bytes(raw: bytes) -> JsonValue:
    """Strict bounded JSON shared by file/config boundaries; raises fixed typed errors."""
    if len(raw) > MAX_BYTES:
        raise InputLimitError
    document = cast(
        JsonValue,
        json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_object,
            parse_float=_finite_float,
            parse_constant=_reject_constant,
        ),
    )
    _check_size(document)
    return document


def check_bytes(raw: bytes) -> Report:
    """Validate one local envelope; never execute, fetch references or log raw data."""
    if len(raw) > MAX_BYTES:
        return incomplete("input_limit_exceeded")
    digest: str | None = None
    try:
        document = parse_json_bytes(raw)
        canonical = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        # Evaluate the same normalized order used by the evidence fingerprint.
        evidence = Evidence.model_validate(json.loads(canonical))
    except (InputLimitError, RecursionError):
        return incomplete("input_limit_exceeded")
    except UnsupportedNumberError:
        return incomplete("unsupported_number")
    except (ValueError, UnicodeError, ModelError):
        return incomplete("invalid_document", digest)
    try:
        return _check(evidence, digest)
    except (RecursionError, MemoryError):
        return incomplete("input_limit_exceeded", digest)
    except Exception:
        # Boundary conversion is explicit failure, never success or silent recovery.
        # Library exceptions may include sensitive instance/schema values.
        return incomplete("checker_error", digest)
