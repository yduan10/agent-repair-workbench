"""A15: build and test against disposable SQLite/API; no model or Docker."""

import os
import subprocess
import tempfile
from pathlib import Path

frontend = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="awb-analysis-e2e-") as directory:
    env = os.environ.copy()
    env.update(
        AWB_ANALYSES_E2E="1",
        AWB_RUNS_E2E="1",
        AWB_STATE_DIR=str(Path(directory) / "state"),
        AWB_API_PORT="8034",
        PW_PORT="3014",
    )
    env.setdefault("PLAYWRIGHT_CHANNEL", "chrome")
    subprocess.run(["npm", "run", "build"], cwd=frontend, env=env, check=True)
    subprocess.run(
        ["npx", "playwright", "test", "tests/analyses-live.spec.ts", "--reporter=line"],
        cwd=frontend,
        env=env,
        check=True,
    )
