"""Two immutable host profiles; no registry, store or oracle imports.

The failure fingerprint belongs to the evaluator. Do not serialize this profile
into a model prompt or expose it as an editable tool argument.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

RepairCaseId = Literal["output_mismatch", "counter_offset"]


@dataclass(frozen=True)
class CaseProfile:
    case_id: RepairCaseId
    resource_directory: str
    manifest_sha256: str
    source_sha256: str
    envelope_sha256: str
    failure_code: Literal["count_type", "count_value"]
    source_relative_path: Literal["source/server.py"] = "source/server.py"
    start_line: Literal[107] = 107
    end_line: Literal[110] = 110

    @property
    def profile_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


_PROFILES = (
    CaseProfile(
        case_id="output_mismatch",
        resource_directory="examples/analysis",
        manifest_sha256="b1743325153cecf414a44c31829087b229cffe66d01574c06680b42b39da6809",
        source_sha256="357abe9daaf18b22c9ed8cd7ca5d3f31776a20afdea7b82b0a66d753316f8712",
        envelope_sha256="890a3f102d895d31b6d3963aa82153df620f5c24a54a430e88f238dab6902cde",
        failure_code="count_type",
    ),
    CaseProfile(
        case_id="counter_offset",
        resource_directory="examples/repair/counter_offset",
        manifest_sha256="81b89fc6fddfa5b1dd1cf173d2a788cedf8646ee3c290b4511b7eb3373b55465",
        source_sha256="b8568ee1bd93e6a35b2015380dba05994c318132ae66841d3d6ccbc1000d96ee",
        envelope_sha256="758339422bcc33ac2cf967d6722d420df2d5e6a0bbfef38008131c854b26e280",
        failure_code="count_value",
    ),
)


def get_profile(case_id: str) -> CaseProfile:
    matches = [p for p in _PROFILES if p.case_id == case_id]
    if len(matches) != 1:
        raise ValueError("unknown_repair_case")
    return matches[0]


def profile_for_manifest(manifest_sha256: str) -> CaseProfile:
    matches = [p for p in _PROFILES if p.manifest_sha256 == manifest_sha256]
    if len(matches) != 1:
        raise ValueError("unknown_repair_manifest")
    return matches[0]
