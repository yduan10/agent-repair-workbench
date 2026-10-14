"""Host-only state and accounting validation independent of model claims."""

from agent_workbench.analysis_store.models import AnalysisEvent
from agent_workbench.orchestration.contracts import AnalysisSummary
from agent_workbench.orchestration.policy import PolicyError, transition
from agent_workbench.run_store.models import StoreError


def validate_update(
    old: AnalysisSummary, new: AnalysisSummary, event: AnalysisEvent, history: list[AnalysisEvent]
) -> None:
    if (
        any(
            getattr(old, field) != getattr(new, field)
            for field in ("task_id", "source_kind", "budget", "started_at")
        )
        or old.state.intent != new.state.intent
    ):
        raise StoreError("analysis_immutable_field")
    if old.model_config_sha256 and new.model_config_sha256 != old.model_config_sha256:
        raise StoreError("analysis_immutable_field")
    if new.state != old.state:
        try:
            expected = transition(
                old.state,
                new.state.phase,
                expected_revision=old.state.revision,
                outcome=new.state.outcome,
            )
            if expected != new.state:
                raise StoreError("analysis_state_conflict")
        except PolicyError:
            raise StoreError("analysis_state_conflict") from None
    if not set(old.evidence_refs) <= set(new.evidence_refs):
        raise StoreError("analysis_evidence_conflict")
    if not set(event.evidence_refs) <= set(new.evidence_refs):
        raise StoreError("analysis_evidence_conflict")
    if new.proposal_count != old.proposal_count + int(
        event.kind == "role_concluded" and event.assessment == "proposal_only"
    ):
        raise StoreError("analysis_accounting_conflict")
    expected_usage = old.usage.model_dump()
    previous = [item for item in history if event.call_id and item.call_id == event.call_id]
    if event.kind in ("model_started", "tool_started"):
        if previous:
            raise StoreError("analysis_call_conflict")
        key = "model_calls" if event.kind == "model_started" else "tool_calls"
        expected_usage[key] += 1
        if event.kind == "model_started":
            if old.usage.reserved_tokens:
                raise StoreError("analysis_unsettled_call")
            assert event.input_reserved is not None and event.output_reserved is not None
            if event.output_reserved > new.budget.output_tokens:
                raise StoreError("analysis_accounting_conflict")
            expected_usage["reserved_tokens"] += event.input_reserved + event.output_reserved
            expected_usage["usage_complete"] = False
    elif event.kind in ("model_settled", "model_unknown", "tool_completed"):
        expected_kind = "tool_started" if event.kind == "tool_completed" else "model_started"
        if len(previous) != 1 or previous[0].kind != expected_kind:
            raise StoreError("analysis_call_conflict")
        start = previous[0]
        if any(
            getattr(start, key) != getattr(event, key)
            for key in (
                "role",
                "tool",
                "request_sha256",
                "input_reserved",
                "output_reserved",
                "reservation_sha256",
            )
        ):
            raise StoreError("analysis_call_conflict")
        if event.kind == "model_settled":
            assert start.input_reserved is not None and start.output_reserved is not None
            assert event.known_input_tokens is not None and event.known_output_tokens is not None
            if (
                event.known_input_tokens > start.input_reserved
                or event.known_output_tokens > start.output_reserved
            ):
                raise StoreError("analysis_accounting_conflict")
            expected_usage["reserved_tokens"] -= start.input_reserved + start.output_reserved
            expected_usage["known_input_tokens"] += event.known_input_tokens
            expected_usage["known_output_tokens"] += event.known_output_tokens
            expected_usage["usage_complete"] = expected_usage["reserved_tokens"] == 0
    if new.usage.model_dump() != expected_usage:
        raise StoreError("analysis_accounting_conflict")
    if (new.state.phase == "finished") != (event.kind in ("finished", "reconciled")):
        raise StoreError("analysis_event_conflict")
    if event.kind == "created":
        raise StoreError("analysis_event_conflict")


def validate_ledger(summary: AnalysisSummary, history: list[AnalysisEvent]) -> None:
    """Rebuild numeric accounting from safe events, without raw response persistence."""
    started: dict[str, AnalysisEvent] = {}
    completed: set[str] = set()
    model_calls = tool_calls = reserved = known_input = known_output = proposals = 0
    for event in history:
        if event.kind in ("model_started", "tool_started"):
            assert event.call_id is not None
            if event.call_id in started:
                raise StoreError("analysis_corrupt")
            started[event.call_id] = event
            if event.kind == "model_started":
                model_calls += 1
                reserved += (event.input_reserved or 0) + (event.output_reserved or 0)
            else:
                tool_calls += 1
        elif event.kind in ("model_settled", "model_unknown", "tool_completed"):
            assert event.call_id is not None
            original = started.get(event.call_id)
            expected = "tool_started" if event.kind == "tool_completed" else "model_started"
            if original is None or original.kind != expected or event.call_id in completed:
                raise StoreError("analysis_corrupt")
            if any(
                getattr(original, key) != getattr(event, key)
                for key in (
                    "role",
                    "tool",
                    "request_sha256",
                    "input_reserved",
                    "output_reserved",
                    "reservation_sha256",
                )
            ):
                raise StoreError("analysis_corrupt")
            completed.add(event.call_id)
            if event.kind == "model_settled":
                if (event.known_input_tokens or 0) > (original.input_reserved or 0) or (
                    event.known_output_tokens or 0
                ) > (original.output_reserved or 0):
                    raise StoreError("analysis_corrupt")
                reserved -= (original.input_reserved or 0) + (original.output_reserved or 0)
                known_input += event.known_input_tokens or 0
                known_output += event.known_output_tokens or 0
        if event.kind == "role_concluded" and event.assessment == "proposal_only":
            proposals += 1
    usage = summary.usage
    if (
        usage.model_calls,
        usage.tool_calls,
        usage.reserved_tokens,
        usage.known_input_tokens,
        usage.known_output_tokens,
        summary.proposal_count,
    ) != (model_calls, tool_calls, reserved, known_input, known_output, proposals):
        raise StoreError("analysis_corrupt")
