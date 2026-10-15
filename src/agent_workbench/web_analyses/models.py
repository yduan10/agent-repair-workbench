"""Fixed browser request and private, once-only admission capabilities."""

from dataclasses import dataclass, field
from typing import Literal

from agent_workbench.analysis_store.models import SaveResult
from agent_workbench.mcp_config import canonical, digest
from agent_workbench.orchestration.contracts import Budget, Contract, Identifier, Intent
from agent_workbench.web_analyses.fencing import AnalysisWebFence

CaseName = Literal["output_mismatch", "passing"]
WEB_BUDGET = Budget(total_tokens=2_000_000, output_tokens=8192)


class AnalysisRequest(Contract):
    request_id: Identifier
    case_name: CaseName
    intent: Intent

    def fingerprint(self) -> str:
        return digest(canonical({"version": 1, **self.model_dump(mode="json")}))


@dataclass(frozen=True)
class AnalysisAdmission:
    saved: SaveResult
    cancel_requested: bool
    claim: "AnalysisClaim | None" = field(default=None, repr=False)


@dataclass(frozen=True)
class AnalysisClaim:
    """Never serialized: only the original live owner receives the token."""

    task_id: str
    initial_sha256: str
    token: str = field(repr=False)
    owner: AnalysisWebFence = field(repr=False)


@dataclass(frozen=True)
class AnalysisStart:
    saved: SaveResult
    cancel_requested: bool
