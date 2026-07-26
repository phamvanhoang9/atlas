"""LangGraph workflow builder — assembles the research pipeline."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.deep_dive import contradiction_check_node, plan_gate_node
from src.agents.generator import generate_report_node, process_context_node
from src.agents.planner import choose_agent_node, generate_sub_queries_node
from src.agents.scope_gate import scope_gate_node
from src.agents.searcher import parallel_search_and_scrape_node, search_and_scrape_node
from src.orchestration.router import (
    route_after_agent_selection,
    route_after_context,
    route_after_plan_gate,
    route_after_scope_gate,
    route_after_search,
    route_search_mode,
)
from src.orchestration.state import ResearchState
from src.quality.evaluation.evaluator import evaluate_state_node


def build_workflow(*, enable_parallel_search: bool = True, enable_evaluation: bool = False) -> StateGraph:
    """Construct and compile the research workflow graph.

    Args:
        enable_parallel_search: Whether to allow parallel multi-query search.
        enable_evaluation: Whether to run optional online evaluation after report generation.

    Returns:
        A compiled LangGraph ``StateGraph``.
    """
    graph = StateGraph(ResearchState)

    # --- nodes ---
    graph.add_node("scope_gate", scope_gate_node)
    graph.add_node("choose_agent", choose_agent_node)
    graph.add_node("plan_gate", plan_gate_node)
    graph.add_node("generate_sub_queries", generate_sub_queries_node)
    graph.add_node("parallel_search_and_scrape", parallel_search_and_scrape_node)
    graph.add_node("search_and_scrape", search_and_scrape_node)
    graph.add_node("process_context", process_context_node)
    graph.add_node("contradiction_check", contradiction_check_node)
    graph.add_node("generate_report", generate_report_node)
    if enable_evaluation:
        graph.add_node("evaluate_report", evaluate_state_node)

    # --- edges ---
    graph.set_entry_point("scope_gate")

    graph.add_conditional_edges(
        "scope_gate",
        route_after_scope_gate,
        {"in_scope": "choose_agent", "refused": END},
    )

    graph.add_conditional_edges(
        "choose_agent",
        route_after_agent_selection,
        {
            "use_provided_urls": "search_and_scrape",
            "plan_gate": "plan_gate",
            "generate_queries": "generate_sub_queries",
        },
    )

    graph.add_conditional_edges(
        "plan_gate",
        route_after_plan_gate,
        {"generate_sub_queries": "generate_sub_queries", "cancelled": END},
    )

    _router = route_search_mode(enable_parallel_search)
    graph.add_conditional_edges(
        "generate_sub_queries",
        _router,
        {"parallel_search": "parallel_search_and_scrape", "sequential_search": "search_and_scrape"},
    )

    graph.add_edge("parallel_search_and_scrape", "process_context")

    graph.add_conditional_edges(
        "search_and_scrape",
        route_after_search,
        {"continue_search": "search_and_scrape", "process_context": "process_context"},
    )

    graph.add_conditional_edges(
        "process_context",
        route_after_context,
        {"contradiction_check": "contradiction_check", "generate_report": "generate_report"},
    )
    graph.add_edge("contradiction_check", "generate_report")

    if enable_evaluation:
        graph.add_edge("generate_report", "evaluate_report")
        graph.add_edge("evaluate_report", END)
    else:
        graph.add_edge("generate_report", END)

    return graph.compile()
