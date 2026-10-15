"""Host-owned web policy fingerprint; request identity remains independent."""

from agent_workbench.candidate_execution.oracle import ORACLE_SHA256, SUITE_SHA256
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.repair_cases.profiles import get_profile

from .models import WEB_BUDGET


def policy_sha256() -> str:
    return digest(
        canonical(
            {
                "version": 1,
                "cases": [
                    get_profile(case).profile_digest
                    for case in ("output_mismatch", "counter_offset")
                ],
                "budget": WEB_BUDGET.model_dump(mode="json"),
                "oracle": ORACLE_SHA256,
                "suite": SUITE_SHA256,
                "container": {"cpu": 0.5, "memory_mib": 128, "pids": 32, "network": "none"},
            }
        )
    )
