"""P0-05b resource boundary probes; no model requests or credentials."""

import shutil
from uuid import uuid4

import pytest

from agent_workbench.controlled_tools.contracts import ReadSource, ToolDecision
from agent_workbench.controlled_tools.resources import load_case, read_verified
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.mcp_config import ROOT, digest
from agent_workbench.orchestration.contracts import Budget, EvidenceRef
from agent_workbench.orchestration.policy import PolicyError, authorize


def registry(root=None, name="output_mismatch"):
    return load_case(
        name,
        task_id=str(uuid4()),
        intent="propose_repair",
        budget=Budget(total_tokens=10000, output_tokens=1000),
        root=root,
    )


def test_reviewed_case_matches_actual_container_source():
    value = registry()
    assert value.initial_report().status == "failed"
    assert any(
        f.instance_path == "/result/structured_content/count"
        for f in value.initial_report().findings
    )
    assert registry(name="passing").initial_report().status == "passed"
    assert (ROOT / "examples/analysis/source/server.py").read_bytes() == (
        ROOT / "containers/p0_03/server.py"
    ).read_bytes()
    request = next(x for x in value.templates("diagnosis") if isinstance(x, ReadSource))
    assert 'str(count) if scenario == "wrong_type"' in value.source(request)["text"]
    assert not any(
        x.tool in ("check_contract", "request_reproduction") for x in value.templates("repair")
    )


def test_dynamic_evidence_has_real_hash_and_task_scope():
    value, other = registry(), registry()
    payload = {"summary": {"status": "failed"}, "findings": [], "events": []}
    ref = value.register(payload)
    assert ref.sha256 == digest(b'{"events":[],"findings":[],"summary":{"status":"failed"}}')
    assert ref in value.task_spec().evidence
    request = next(
        x
        for x in value.templates("diagnosis")
        if x.tool == "read_evidence" and x.evidence_ref == ref
    )
    authorize(
        value.task_spec(),
        "diagnosis",
        ToolDecision(action="request_tool", request=request),
        value.authorization(),
    )
    with pytest.raises(PolicyError):
        authorize(
            other.task_spec(),
            "diagnosis",
            ToolDecision(action="request_tool", request=request),
            other.authorization(),
        )
    with pytest.raises(ResourceError, match="PERMISSION_DENIED"):
        other.evidence(ref, "summary")
    with pytest.raises(ResourceError, match="PERMISSION_DENIED"):
        value.evidence(EvidenceRef(evidence_id=ref.evidence_id, sha256="f" * 64), "summary")
    assert value.register(payload) == ref
    payload["summary"]["status"] = "tampered"
    assert value.evidence(ref, "summary")["summary"]["status"] == "failed"


def test_grants_reference_limit_stops_instead_of_evicting():
    value = registry()
    for i in range(31):
        value.register({"summary": {"count": i}, "findings": [], "events": []})
    assert len(value.task_spec().evidence) == 32
    assert len(value.authorization().allowed_targets) == 100
    with pytest.raises(ResourceError, match="RESOURCE_LIMIT"):
        value.register({"summary": {"count": 32}})


@pytest.mark.parametrize("kind", ["file", "directory", "ancestor", "hardlink", "fifo"])
def test_full_path_symlink_and_special_file_rejected(tmp_path, kind):
    root = tmp_path.resolve() / "root"
    root.mkdir()
    real = tmp_path.resolve() / "real"
    real.write_bytes(b"synthetic")
    wanted = root / "source.py"
    if kind == "file":
        wanted.symlink_to(real)
    elif kind == "directory":
        directory = root / "source"
        directory.symlink_to(tmp_path.resolve(), target_is_directory=True)
        wanted = directory / "real"
    elif kind == "ancestor":
        alias = tmp_path.resolve() / "alias"
        alias.symlink_to(root, target_is_directory=True)
        wanted.write_bytes(b"synthetic")
        root = alias
        wanted = root / "source.py"
    elif kind == "hardlink":
        wanted.hardlink_to(real)
    else:
        import os

        os.mkfifo(wanted)
    with pytest.raises(ResourceError, match="PERMISSION_DENIED"):
        read_verified(root, str(wanted.relative_to(root)), digest(b"synthetic"))


def test_source_hash_changed_after_registry_creation(tmp_path):
    root = tmp_path.resolve() / "reviewed"
    shutil.copytree(ROOT / "examples/analysis", root)
    value = registry(root)
    request = next(x for x in value.templates("diagnosis") if x.tool == "read_source")
    (root / "source/server.py").write_text("SECRET_AFTER_REVIEW")
    with pytest.raises(ResourceError, match="ARTIFACT_MISMATCH") as error:
        value.source(request)
    assert "SECRET" not in str(error.value)


def test_whole_file_size_and_hash_limits(tmp_path):
    root = tmp_path.resolve()
    (root / "big.py").write_bytes(b"x" * 131073)
    with pytest.raises(ResourceError, match="RESOURCE_LIMIT"):
        read_verified(root, "big.py", "f" * 64)
    (root / "small.py").write_bytes(b"actual")
    with pytest.raises(ResourceError, match="ARTIFACT_MISMATCH"):
        read_verified(root, "small.py", "f" * 64)


def test_manifest_tampering_rejected(tmp_path):
    root = tmp_path.resolve() / "reviewed"
    shutil.copytree(ROOT / "examples/analysis", root)
    (root / "manifest.json").write_text("{}")
    with pytest.raises(ResourceError, match="ARTIFACT_MISMATCH"):
        registry(root)
