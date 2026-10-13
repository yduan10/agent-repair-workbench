"""Bounded JSON decoder. Public errors never include input or validation details."""

import json
import math
from typing import TypeVar

from pydantic import TypeAdapter

from agent_workbench.agents.diagnosis.contracts import DiagnosisOutput
from agent_workbench.agents.repair.contracts import RepairOutput
from agent_workbench.agents.verification.contracts import VerificationOutput
from agent_workbench.orchestration.contracts import Role
from agent_workbench.orchestration.policy import PolicyError, RoleOutput

MAX_MESSAGE_BYTES = 65536

DIAGNOSIS_ADAPTER = TypeAdapter[DiagnosisOutput](DiagnosisOutput)
REPAIR_ADAPTER = TypeAdapter[RepairOutput](RepairOutput)
VERIFICATION_ADAPTER = TypeAdapter[VerificationOutput](VerificationOutput)
T = TypeVar("T")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise ValueError("non_finite_number")


def decode[T](raw: bytes, adapter: TypeAdapter[T]) -> T:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise PolicyError("MESSAGE_LIMIT_EXCEEDED")
    try:
        # Preflight preserves original bytes; validate_json provides strict JSON tuple/datetime
        # semantics without making Python-mode coercions or allowing duplicate keys.
        parsed: object = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant
        )
        pending = [(parsed, 0)]
        while pending:
            value, depth = pending.pop()
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("non_finite_number")
            if depth > 20:
                raise ValueError("depth_limit")
            if isinstance(value, dict):
                pending.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
        return adapter.validate_json(raw)
    except (ValueError, RecursionError, UnicodeError):
        raise PolicyError("INVALID_MESSAGE") from None


def decode_role(raw: bytes, role: Role) -> RoleOutput:
    if role == "diagnosis":
        return decode(raw, DIAGNOSIS_ADAPTER)
    if role == "repair":
        return decode(raw, REPAIR_ADAPTER)
    if role == "verification":
        return decode(raw, VERIFICATION_ADAPTER)
    raise PolicyError("UNKNOWN_ROLE")
