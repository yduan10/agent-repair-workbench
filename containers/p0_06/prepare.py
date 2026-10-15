"""Explicit, offline P0-06 launcher image preparation. Never invoked on client startup."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIGEST = "python@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
IMAGE_TAG = "awb-p0-06:local"
# Exact ENV inherited from the pinned official Python base, verified locally by digest.
EXPECTED_ENV = (
    "PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG=C.UTF-8",
    "GPG_KEY=7169605F62C751356D054A26A821E680E5FA6305",
    "PYTHON_VERSION=3.12.14",
    "PYTHON_SHA256=5c8462af5790baf43a321a1559dbe0db06d1be4300fb85fb53c40060668e548a",
)
EXPECTED_ENTRYPOINT = ["python", "-I", "-B", "/opt/guardian/supervisor.py"]
SOURCE_FILES = ("Dockerfile", "supervisor.py", "prepare.py")
SOURCE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SOURCE_DIR.parent.parent


def source_sha256(source_dir: Path = SOURCE_DIR) -> str:
    parts = []
    for name in SOURCE_FILES:
        path = source_dir / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("source_unavailable")
        parts.append(name.encode() + b"\0" + path.read_bytes())
    return hashlib.sha256(b"\0".join(parts)).hexdigest()


def prepare() -> dict[str, str]:
    original = source_sha256()
    # Fail before build if the pinned base is absent; never let build obtain a new base.
    subprocess.run(
        ["docker", "image", "inspect", BASE_DIGEST],
        check=True,
        timeout=5,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # A minimal temporary build context prevents accidentally sending unrelated files to Docker.
    with tempfile.TemporaryDirectory(prefix="awb-p0-06-build-") as directory:
        context = Path(directory) / "context"
        context.mkdir()
        iidfile = Path(directory) / "image.id"
        for name in ("Dockerfile", "supervisor.py"):
            (context / name).write_bytes((SOURCE_DIR / name).read_bytes())
        subprocess.run(
            [
                "docker",
                "build",
                "--network=none",
                "--pull=false",
                "--build-arg",
                f"BASE={BASE_DIGEST}",
                "--tag",
                IMAGE_TAG,
                "--iidfile",
                str(iidfile),
                str(context),
            ],
            check=True,
            timeout=120,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # The shared tag may change concurrently; only this build's iidfile identifies its image.
        if iidfile.is_symlink() or not iidfile.is_file() or iidfile.stat().st_size > 128:
            raise ValueError("invalid_image_id")
        image_id = iidfile.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise ValueError("invalid_image_id")
        inspected = subprocess.run(
            ["docker", "image", "inspect", image_id],
            check=True,
            timeout=5,
            capture_output=True,
            text=True,
        )
        images = json.loads(inspected.stdout)
        if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
            raise ValueError("invalid_image_config")
        image = images[0]
        config = image.get("Config")
        if image.get("Id") != image_id or not isinstance(config, dict):
            raise ValueError("invalid_image_config")
        environment = config.get("Env")
        if (
            config.get("Entrypoint") != EXPECTED_ENTRYPOINT
            or config.get("User") != "65532:65532"
            or config.get("WorkingDir") != "/tmp"
            or config.get("Volumes") not in (None, {})
            or not isinstance(environment, list)
            or not all(isinstance(item, str) for item in environment)
            or sorted(environment) != sorted(EXPECTED_ENV)
        ):
            raise ValueError("invalid_image_config")
    if original != source_sha256():
        raise ValueError("source_changed")
    manifest = {"image_id": image_id, "source_sha256": original, "base_digest": BASE_DIGEST}
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    target = artifacts / "p0-06-image.json"
    # Explicit prepare is the only writer; atomic replacement avoids partial reader observations.
    descriptor, temp = tempfile.mkstemp(prefix=".p0-06-image-", dir=artifacts)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temp, target)
    finally:
        Path(temp).unlink(missing_ok=True)
    return manifest


def main() -> int:
    if len(sys.argv) != 1:
        print('{"code":"invalid_arguments"}', file=sys.stderr)
        return 2
    try:
        result = prepare()
    except subprocess.TimeoutExpired:
        code = "image_prepare_timeout"
    except (OSError, ValueError, subprocess.CalledProcessError):
        code = "image_prepare_failed"
    else:
        print(json.dumps(result, sort_keys=True))
        return 0
    print(json.dumps({"code": code}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
