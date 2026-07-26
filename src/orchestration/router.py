"""Routing functions for conditional edges in the research graph."""

from __future__ import annotations

from typing import Callable

from src.modes import DEEP_DIVE, normalize_mode
from src.orchestration.state import ResearchState


def route_after_scope_gate(state: ResearchState) -> str:
    """Stop the workflow when the scope gate refused the query."""
    if state.get("scope_refusal"):
        return "refused"
    return "in_scope"


def route_after_agent_selection(state: ResearchState) -> str:
    """Decide whether to use provided URLs, gate on a plan, or generate queries.

    Direct source URLs always bypass planning (same behavior for every
    mode, unchanged from before Giai đoạn 4). Otherwise deep_dive routes
    through plan_gate first; ask/compare go straight to query generation,
    exactly as before.
    """
    if state.get("source_urls") and len(state["source_urls"]) > 0:
        return "use_provided_urls"
    if normalize_mode(state.get("report_type")) == DEEP_DIVE:
        return "plan_gate"
    return "generate_queries"


def route_after_plan_gate(state: ResearchState) -> str:
    """Continue to search only once the Deep Dive plan is approved.

    Fails closed: a missing/False plan_approved (rejected, timed out,
    disconnected, or an invalid client response) cancels the run rather
    than silently proceeding.
    """
    if state.get("plan_approved") is True:
        return "generate_sub_queries"
    return "cancelled"


def route_after_context(state: ResearchState) -> str:
    """Run the contradiction check only for deep_dive; ask/compare go straight to the report, unchanged."""
    if normalize_mode(state.get("report_type")) == DEEP_DIVE:
        return "contradiction_check"
    return "generate_report"


def route_search_mode(enable_parallel: bool) -> Callable[[ResearchState], str]:
    """Return a router that picks parallel or sequential search."""

    def _router(state: ResearchState) -> str:
        sub_queries = state.get("sub_queries", [])
        if enable_parallel and len(sub_queries) > 1:
            return "parallel_search"
        return "sequential_search"

    return _router


def route_after_search(state: ResearchState) -> str:
    """Decide whether to continue searching or move to context processing."""
    current_index = state.get("current_query_index", 0)
    total_queries = len(state.get("sub_queries", []))
    if current_index < total_queries:
        return "continue_search"
    return "process_context"
