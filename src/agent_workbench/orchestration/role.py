"""Ephemeral role contexts; no raw text enters graph state, traces or storage."""

from dataclasses import dataclass

from agent_workbench.model_gateway.gateway import canonical
from agent_workbench.orchestration.codec import decode_role
from agent_workbench.orchestration.contracts import Role
from agent_workbench.orchestration.policy import RoleOutput


@dataclass(frozen=True)
class RoleAgent:
    role: Role
    system_prompt: str

    def messages(self, context: object) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": canonical(context).decode("ascii")},
        ]

    def decode(self, raw: bytes) -> RoleOutput:
        return decode_role(raw, self.role)
