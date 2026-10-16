"""B3 macOS LaunchAgents. No credentials in plists; no migration or builds at startup."""

import argparse
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "artifacts/local-service"
LABELS = {"api": "io.agentrepair.local.api", "web": "io.agentrepair.local.web"}
ALLOWED = frozenset(
    {
        "AWB_MODEL_BASE_URL",
        "AWB_MODEL_NAME",
        "AWB_MODEL_API_KEY",
        "AWB_MODEL_LIMIT_PROFILE",
        "AWB_MODEL_INPUT_PRICE_PER_MILLION",
        "AWB_MODEL_OUTPUT_PRICE_PER_MILLION",
    }
)


def read_environment(path: Path) -> dict[str, str]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("private_environment_required")
    if info.st_size > 16384:
        raise ValueError("environment_too_large")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) - ALLOWED:
        raise ValueError("invalid_environment_keys")
    if any(not isinstance(v, str) or not v or "\x00" in v for v in value.values()):
        raise ValueError("invalid_environment_value")
    return value


def specification(kind: str, root: Path, node: str) -> dict[str, object]:
    local = root / "artifacts/local-service"
    args = (
        [str(root / ".venv/bin/python"), str(root / "ops/local_service.py"), "serve-api"]
        if kind == "api"
        else [
            node,
            str(root / "frontend/node_modules/next/dist/bin/next"),
            "start",
            "--hostname",
            "127.0.0.1",
            "--port",
            "3010",
        ]
    )
    return {
        "Label": LABELS[kind],
        "ProgramArguments": args,
        "WorkingDirectory": str(root if kind == "api" else root / "frontend"),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "NODE_ENV": "production",
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ExitTimeOut": 660,
        "StandardOutPath": str(local / f"{kind}.log"),
        "StandardErrorPath": str(local / f"{kind}.log"),
        "Umask": 0o077,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "stop", "status", "serve-api"])
    args = parser.parse_args()
    if args.command == "serve-api":
        import uvicorn

        os.environ.update(read_environment(LOCAL / "model-env.json"))
        os.environ.update(AWB_STATE_DIR=str(ROOT / "artifacts/run-store"), AWB_FRONTEND_PORT="3010")
        uvicorn.run("agent_workbench.api:app", host="127.0.0.1", port=8030, access_log=False)
        return
    if sys.platform != "darwin":
        raise ValueError("macos_required")
    domain = f"gui/{os.getuid()}"
    folder = Path.home() / "Library/LaunchAgents"
    if args.command == "status":
        for label in LABELS.values():
            subprocess.run(["launchctl", "print", f"{domain}/{label}"], check=False)
        return
    node = shutil.which("node")
    if not node:
        raise ValueError("node_required")

    def loaded(label: str) -> bool:
        result = subprocess.run(
            ["launchctl", "print", f"{domain}/{label}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode not in (0, 113):
            raise ValueError("service_status_unavailable")
        if result.returncode == 0 and str(ROOT).encode() not in result.stdout:
            raise ValueError("loaded_service_checkout_mismatch")
        return result.returncode == 0

    def check_file(kind: str, required: bool = False) -> Path:
        path = folder / f"{LABELS[kind]}.plist"
        if path.exists() or path.is_symlink():
            if path.is_symlink() or plistlib.loads(path.read_bytes()) != specification(
                kind, ROOT, node
            ):
                raise ValueError("existing_service_configuration_mismatch")
        elif required:
            raise ValueError("service_configuration_missing")
        return path

    def wait_unloaded(label: str) -> bool:
        # bootout may return before launchd removes the registration.
        for _ in range(50):
            if not loaded(label):
                return True
            time.sleep(0.1)
        return not loaded(label)

    if args.command == "stop":
        active = [kind for kind, label in LABELS.items() if loaded(label)]
        for kind in active:
            check_file(kind, required=True)
        failed = False
        for kind in reversed(active):
            result = subprocess.run(
                ["launchctl", "bootout", f"{domain}/{LABELS[kind]}"], check=False
            )
            failed = result.returncode != 0 or not wait_unloaded(LABELS[kind]) or failed
        if failed:
            raise ValueError("service_stop_failed")
        return
    if (
        not (ROOT / ".venv/bin/python").is_file()
        or not (ROOT / "frontend/.next/BUILD_ID").is_file()
    ):
        raise ValueError("prepare_python_and_production_build_first")
    read_environment(LOCAL / "model-env.json")
    folder.mkdir(parents=True, exist_ok=True)
    paths = {kind: check_file(kind) for kind in LABELS}
    if any(loaded(label) for label in LABELS.values()):
        raise ValueError("service_already_loaded_stop_before_restart")
    # Validate both services before making either runnable. Roll back only this install.
    installed: list[str] = []
    try:
        for kind, path in paths.items():
            if not path.exists():
                with path.open("xb") as output:
                    os.chmod(path, 0o600)
                    plistlib.dump(specification(kind, ROOT, node), output)
        for kind, path in paths.items():
            # Track even an ambiguous bootstrap outcome so it is also stopped on failure.
            installed.append(LABELS[kind])
            subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    except Exception:
        for label in reversed(installed):
            subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], check=False)
        if any(not wait_unloaded(label) for label in installed):
            raise ValueError("install_rollback_incomplete") from None
        raise
    for label in installed:
        print(f"installed {label}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Configuration may contain credentials: deliberately do not print exception text.
        print(
            "Local service operation failed. Check prerequisites and private configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
