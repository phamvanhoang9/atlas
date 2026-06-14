"""Routing functions for conditional edges in the research graph."""

from __future__ import annotations

from typing import Callable

from src.orchestration.state import ResearchState


def route_after_scope_gate(state: ResearchState) -> str:
    """Stop the workflow when the scope gate refused the query."""
    if state.get("scope_refusal"):
        return "refused"
    return "in_scope"


def route_after_agent_selection(state: ResearchState) -> str:
    """Decide whether to use provided URLs or generate queries."""
    if state.get("source_urls") and len(state["source_urls"]) > 0:
        return "use_provided_urls"
    return "generate_queries"


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
