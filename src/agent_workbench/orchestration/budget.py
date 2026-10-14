"""Pure token accounting. A reservation is not a measured token charge."""

from agent_workbench.model_gateway.gateway import PreparedCall, Reply
from agent_workbench.orchestration.contracts import AnalysisSummary, Usage
from agent_workbench.orchestration.policy import PolicyError


def reserve(summary: AnalysisSummary, request: PreparedCall) -> Usage:
    current = summary.usage
    if (
        not current.usage_complete
        or current.model_calls >= summary.budget.model_calls
        or request.output_reserved > summary.budget.output_tokens
        or min(request.input_reserved, request.output_reserved) < 0
        or request.input_reserved
        + request.output_reserved
        + current.known_input_tokens
        + current.known_output_tokens
        > summary.budget.total_tokens
    ):
        raise PolicyError("BUDGET_EXCEEDED")
    return Usage(
        model_calls=current.model_calls + 1,
        tool_calls=current.tool_calls,
        reserved_tokens=request.input_reserved + request.output_reserved,
        known_input_tokens=current.known_input_tokens,
        known_output_tokens=current.known_output_tokens,
        usage_complete=False,
    )


def settle(current: Usage, request: PreparedCall, reply: Reply) -> Usage:
    if not reply.usage_known:
        return current
    i, o = reply.input_tokens, reply.output_tokens
    if (
        type(i) is not int
        or type(o) is not int
        or i < 0
        or o < 0
        or i > request.input_reserved
        or o > request.output_reserved
        or current.reserved_tokens != request.input_reserved + request.output_reserved
    ):
        raise PolicyError("MODEL_USAGE_BOUND_VIOLATION")
    return Usage(
        model_calls=current.model_calls,
        tool_calls=current.tool_calls,
        known_input_tokens=current.known_input_tokens + i,
        known_output_tokens=current.known_output_tokens + o,
        reserved_tokens=0,
        usage_complete=True,
    )
