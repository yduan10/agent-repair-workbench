"""Run UI tests against a disposable real SQLite/API, outside user data (no Docker)."""

import os
import subprocess
import tempfile
from pathlib import Path

frontend = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="awb-p004-e2e-") as directory:
    env = os.environ.copy()
    env.update(
        AWB_RUNS_E2E="1",
        AWB_STATE_DIR=str(Path(directory) / "state"),
        AWB_API_PORT="8031",
        PW_PORT="3011",
    )
    env.setdefault("PLAYWRIGHT_CHANNEL", "chrome")
    subprocess.run(["npm", "run", "build"], cwd=frontend, env=env, check=True)
    subprocess.run(
        [
            "npx",
            "playwright",
            "test",
            "tests/runs-live.spec.ts",
            "tests/runs.spec.ts",
            "tests/appearance.spec.ts",
            "tests/progress.spec.ts",
            "--reporter=line",
        ],
        cwd=frontend,
        env=env,
        check=True,
    )
