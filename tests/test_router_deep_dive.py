"""Tests for the Giai đoạn 4 routing additions.

route_after_agent_selection gains a 3rd branch (plan_gate, deep_dive only);
route_after_plan_gate and route_after_context are new. Ask/Compare behavior
through route_after_agent_selection must be provably unchanged (doubt-driven
review contract #2).
"""

from src.orchestration.router import (
    route_after_agent_selection,
    route_after_context,
    route_after_plan_gate,
)


def _state(**overrides):
    state = {"report_type": "ask", "source_urls": []}
    state.update(overrides)
    return state


# --------------------------------------------------------------------------
# route_after_agent_selection — ask/compare unchanged, deep_dive gains plan_gate
# --------------------------------------------------------------------------


def test_ask_without_urls_generates_queries_unchanged():
    assert route_after_agent_selection(_state(report_type="ask")) == "generate_queries"


def test_compare_without_urls_generates_queries_unchanged():
    assert route_after_agent_selection(_state(report_type="compare")) == "generate_queries"


def test_ask_with_urls_uses_provided_urls_unchanged():
    state = _state(report_type="ask", source_urls=["https://a.example"])
    assert route_after_agent_selection(state) == "use_provided_urls"


def test_compare_with_urls_uses_provided_urls_unchanged():
    state = _state(report_type="compare", source_urls=["https://a.example"])
    assert route_after_agent_selection(state) == "use_provided_urls"


def test_deep_dive_without_urls_routes_to_plan_gate():
    assert route_after_agent_selection(_state(report_type="deep_dive")) == "plan_gate"


def test_deep_dive_with_urls_bypasses_plan_gate():
    """Direct source URLs skip planning, same bypass as today for other modes."""
    state = _state(report_type="deep_dive", source_urls=["https://a.example"])
    assert route_after_agent_selection(state) == "use_provided_urls"


def test_unknown_mode_falls_back_to_compare_behavior():
    """normalize_mode() defaults unknown report_types to compare — routing must match."""
    assert route_after_agent_selection(_state(report_type="something_unknown")) == "generate_queries"


# --------------------------------------------------------------------------
# route_after_plan_gate
# --------------------------------------------------------------------------


def test_plan_approved_continues_to_sub_queries():
    assert route_after_plan_gate({"plan_approved": True}) == "generate_sub_queries"


def test_plan_rejected_ends_workflow():
    assert route_after_plan_gate({"plan_approved": False}) == "cancelled"


def test_plan_approved_missing_defaults_to_cancelled():
    """Absent key must fail closed, not silently proceed."""
    assert route_after_plan_gate({}) == "cancelled"


# --------------------------------------------------------------------------
# route_after_context
# --------------------------------------------------------------------------


def test_deep_dive_routes_to_contradiction_check():
    assert route_after_context(_state(report_type="deep_dive")) == "contradiction_check"


def test_ask_routes_directly_to_report_unchanged():
    assert route_after_context(_state(report_type="ask")) == "generate_report"


def test_compare_routes_directly_to_report_unchanged():
    assert route_after_context(_state(report_type="compare")) == "generate_report"
