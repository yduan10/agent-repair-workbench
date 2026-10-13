"""P0-02: exact issue #3644 model, registered through the pinned SDK server.

No source or schema patch is applied. Input/output are public synthetic values.
"""

import sys
from pathlib import Path

COMMIT = "2118f14f8a19bc158d8a1cf90af58d85d187f849"
SOURCE = (
    Path(__file__).resolve().parents[2] / "artifacts" / "public-mcp-case" / f"python-sdk-{COMMIT}"
)
sys.path[:0] = [str(SOURCE / "src"), str(SOURCE / "src/mcp-types")]

from mcp.server.mcpserver import MCPServer  # noqa: E402
from pydantic import BaseModel, Field, computed_field  # noqa: E402


class Out(BaseModel):
    user_id: int = Field(serialization_alias="userId")

    @computed_field
    @property
    def doubled(self) -> int:
        return self.user_id * 2


server = MCPServer("public-issue-3644", version=COMMIT, log_level="ERROR")


@server.tool()
def tool() -> Out:
    """Return the public issue's minimal model."""
    return Out(user_id=3)


if __name__ == "__main__":
    server.run(transport="stdio")
