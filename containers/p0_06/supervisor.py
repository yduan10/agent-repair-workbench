"""Auxiliary launcher only. The host owns the deadline, oracle and cleanup.

A same-UID candidate may signal this process; host death is NOT a hard-expiry
promise. No result text from this launcher is accepted as verification evidence.
"""

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=("pass", "wrong_type"))
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        return 2
    child = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "/opt/subject/server.py",
            "--worker",
            "--scenario",
            args.scenario,
            "--seed",
            "0",
            "--lifetime",
            "45",
        ],
        start_new_session=True,
    )
    try:
        return child.wait(timeout=45)
    except subprocess.TimeoutExpired:
        return 124
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
