"""P0-05b host-owned reviewed resources; model messages cannot register capabilities."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import JsonValue, TypeAdapter

from agent_workbench.checker import parse_json_bytes
from agent_workbench.cli import run_check
from agent_workbench.controlled_tools.contracts import (
    CheckContract,
    ReadContract,
    ReadEvidence,
    ReadSource,
    RelativePath,
    Reproduce,
    ToolRequest,
    target_key,
)
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.mcp_config import ROOT, CallCase, canonical, digest
from agent_workbench.models import Evidence, Report
from agent_workbench.orchestration.contracts import (
    Budget,
    Contract,
    Digest,
    EvidenceRef,
    Intent,
    Role,
    TaskSpec,
)
from agent_workbench.orchestration.policy import ROLE_TOOLS, AuthorizationContext, EditableFile
from agent_workbench.runner.models import SandboxConfig

MANIFEST_SHA256 = "b1743325153cecf414a44c31829087b229cffe66d01574c06680b42b39da6809"
MAX_FILE = 131_072
SECTIONS: tuple[Literal["summary", "findings", "events"], ...] = ("summary", "findings", "events")
_CASE_IDS = {
    name: str(uuid5(NAMESPACE_URL, "awb:synthetic-analysis:" + name))
    for name in ("output_mismatch", "passing")
}


class SourceEntry(Contract):
    path: RelativePath
    sha256: Digest
    start_line: int
    end_line: int


class CaseManifest(Contract):
    version: Literal[1]
    source: SourceEntry
    envelopes: dict[str, Digest]


def read_verified(root: Path, relative: str, expected: str) -> bytes:
    """Open every component without following links, then hash the opened regular file."""
    parts = (*root.absolute().parts[1:], *relative.split("/"))
    if not parts or any(part in ("", ".", "..") or "/" in part for part in parts):
        raise ResourceError("PERMISSION_DENIED")
    descriptors: list[int] = []
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        descriptors.append(descriptor)
        for part in parts[:-1]:
            descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            descriptors.append(descriptor)
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=descriptor,
        )
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ResourceError("PERMISSION_DENIED")
        if before.st_size > MAX_FILE:
            raise ResourceError("RESOURCE_LIMIT")
        chunks = bytearray()
        while len(chunks) <= MAX_FILE:
            chunk = os.read(descriptor, min(8192, MAX_FILE + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
        after = os.fstat(descriptor)
        if len(chunks) > MAX_FILE:
            raise ResourceError("RESOURCE_LIMIT")
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or digest(bytes(chunks)) != expected:
            raise ResourceError("ARTIFACT_MISMATCH")
        return bytes(chunks)
    except OSError:
        raise ResourceError("PERMISSION_DENIED") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@dataclass(frozen=True)
class _EvidenceRecord:
    task_id: str
    ref: EvidenceRef
    raw: bytes


class TaskResourceRegistry:
    """A capability is scoped to one task. Construction/registration is host-only."""

    def __init__(
        self,
        *,
        task_id: str,
        intent: Intent,
        budget: Budget,
        case_name: Literal["output_mismatch", "passing"],
        root: Path,
    ) -> None:
        self._root = root
        self._records: dict[str, _EvidenceRecord] = {}
        manifest = CaseManifest.model_validate_json(
            read_verified(root, "manifest.json", MANIFEST_SHA256)
        )
        self.case_name = case_name
        self.case_id = _CASE_IDS[case_name]
        self._raw = read_verified(root, case_name + ".json", manifest.envelopes[case_name])
        evidence = Evidence.model_validate(parse_json_bytes(self._raw))
        self._contract = canonical(evidence.tool.model_dump(mode="json"))
        self.contract_revision = digest(self._contract)
        self._source = manifest.source
        self.snapshot_id = digest(canonical(self._source.model_dump(mode="json")))
        self._config = canonical(
            SandboxConfig(
                scenario="wrong_type" if case_name == "output_mismatch" else "pass"
            ).model_dump(mode="json")
        )
        self._case = canonical(
            CallCase(case_id="synthetic-lookup", tool="lookup", arguments={"id": 1}).model_dump(
                mode="json"
            )
        )
        # Both scenario and exact input bytes are part of the approved execution revision.
        self.profile_revision = digest(
            canonical(
                {
                    "config_sha256": digest(self._config),
                    "case_sha256": digest(self._case),
                    "source_sha256": manifest.source.sha256,
                }
            )
        )
        self._task_id = task_id
        self._initial_report = run_check(self._raw, 5)
        ref = self.register(
            {
                "summary": self._initial_report.model_dump(mode="json", exclude={"findings"}),
                "findings": [
                    item.model_dump(mode="json") for item in self._initial_report.findings
                ],
                "events": [],
            }
        )
        budget = Budget.model_validate_json(budget.model_dump_json())
        self._original = TaskSpec(
            task_id=task_id,
            intent=intent,
            source_kind="synthetic",
            budget=budget,
            evidence=(ref,),
        )

    def ensure_capacity(self) -> None:
        if len(self._records) >= 32:
            raise ResourceError("RESOURCE_LIMIT")

    def task_spec(self) -> TaskSpec:
        value = self._original.model_dump(mode="python")
        value["evidence"] = tuple(record.ref for record in self._records.values())
        return TaskSpec.model_validate(value)

    def initial_report(self) -> Report:
        return Report.model_validate_json(self._initial_report.model_dump_json())

    def register(self, payload: dict[str, JsonValue]) -> EvidenceRef:
        """Register safe host-built metadata only. No model request exposes this operation."""
        raw = canonical(payload)
        if len(raw) > 48_000:
            raise ResourceError("RESOURCE_LIMIT")
        for record in self._records.values():
            if record.raw == raw:
                return EvidenceRef.model_validate(record.ref.model_dump(mode="python"))
        if len(self._records) >= 32:
            raise ResourceError("RESOURCE_LIMIT")
        ref = EvidenceRef(evidence_id=str(uuid4()), sha256=digest(raw))
        self._records[ref.evidence_id] = _EvidenceRecord(self._task_id, ref, raw)
        return EvidenceRef.model_validate(ref.model_dump(mode="python"))

    def evidence(self, ref: EvidenceRef, section: str) -> dict[str, JsonValue]:
        record = self._records.get(ref.evidence_id)
        if record is None or record.task_id != self._task_id or record.ref != ref:
            raise ResourceError("PERMISSION_DENIED")
        if digest(record.raw) != ref.sha256:
            raise ResourceError("ARTIFACT_MISMATCH")
        value = TypeAdapter(dict[str, JsonValue]).validate_json(record.raw)
        return {section: value.get(section, [])}

    def templates(self, role: Role) -> tuple[ToolRequest, ...]:
        source = self._source
        all_requests: list[ToolRequest] = [
            ReadEvidence(
                tool="read_evidence",
                request_id=str(uuid4()),
                evidence_ref=record.ref,
                section=section,
            )
            for record in self._records.values()
            for section in SECTIONS
        ]
        all_requests.extend(
            (
                ReadContract(
                    tool="read_contract",
                    request_id=str(uuid4()),
                    profile_id="isolated-fixture",
                    tool_name="lookup",
                    revision=self.contract_revision,
                ),
                ReadSource(
                    tool="read_source",
                    request_id=str(uuid4()),
                    snapshot_id=self.snapshot_id,
                    relative_path=source.path,
                    start_line=source.start_line,
                    end_line=source.end_line,
                ),
                CheckContract(
                    tool="check_contract",
                    request_id=str(uuid4()),
                    case_id=self.case_id,
                    contract_revision=self.contract_revision,
                ),
                Reproduce(
                    tool="request_reproduction",
                    request_id=str(uuid4()),
                    approved_case_id=self.case_id,
                    profile_revision=self.profile_revision,
                ),
            )
        )
        return tuple(item for item in all_requests if item.tool in ROLE_TOOLS[role])

    request_templates = templates

    def authorization(self) -> AuthorizationContext:
        source = self._source
        return AuthorizationContext(
            task_id=self._task_id,
            evidence_refs=self.task_spec().evidence,
            allowed_targets=tuple(target_key(item) for item in self.templates("diagnosis")),
            editable_files=(EditableFile(path=source.path, base_sha256=source.sha256),),
        )

    def contract(self) -> dict[str, JsonValue]:
        self.verify_case()
        if digest(self._contract) != self.contract_revision:
            raise ResourceError("ARTIFACT_MISMATCH")
        return TypeAdapter(dict[str, JsonValue]).validate_json(self._contract)

    def source(self, request: ReadSource) -> dict[str, JsonValue]:
        source = self._source
        if request.snapshot_id != self.snapshot_id or request.relative_path != source.path:
            raise ResourceError("PERMISSION_DENIED")
        raw = read_verified(self._root, source.path, source.sha256)
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise ResourceError("ARTIFACT_MISMATCH") from None
        lines = text.splitlines(keepends=True)
        if request.end_line > len(lines):
            raise ResourceError("INVALID_INPUT")
        snippet = "".join(lines[request.start_line - 1 : request.end_line])
        if "\0" in snippet or len(snippet.encode("utf-8")) > 16_384:
            raise ResourceError("RESOURCE_LIMIT")
        return {
            "path": request.relative_path,
            "start_line": request.start_line,
            "end_line": request.end_line,
            "file_sha256": source.sha256,
            "snapshot_id": self.snapshot_id,
            "text": snippet,
        }

    def verify_case(self) -> bytes:
        manifest = CaseManifest.model_validate_json(
            read_verified(self._root, "manifest.json", MANIFEST_SHA256)
        )
        raw = read_verified(
            self._root, self.case_name + ".json", manifest.envelopes[self.case_name]
        )
        if raw != self._raw:
            raise ResourceError("ARTIFACT_MISMATCH")
        return raw

    def source_sha256(self) -> str:
        return self._source.sha256

    def reproduction(self) -> tuple[bytes, bytes]:
        self.verify_case()
        source = self._source
        read_verified(self._root, source.path, source.sha256)
        return self._config, self._case


def load_case(
    case_name: Literal["output_mismatch", "passing"],
    *,
    task_id: str,
    intent: Intent,
    budget: Budget,
    root: Path | None = None,
) -> TaskResourceRegistry:
    if case_name not in _CASE_IDS:
        raise ResourceError("INVALID_INPUT")
    return TaskResourceRegistry(
        task_id=task_id,
        intent=intent,
        budget=budget,
        case_name=case_name,
        root=root if root is not None else ROOT / "examples/analysis",
    )
