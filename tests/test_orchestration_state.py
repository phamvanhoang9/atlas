"""Tests for the Giai đoạn 4 additive ResearchState keys.

These keys (research_plan, plan_approved, scored_sources, contradictions,
confidence_trace, run_id, headless) must be NotRequired so existing
ask/compare code paths that never set them keep working unmodified.
"""

from typing import get_type_hints

from src.orchestration.state import ResearchState


def test_new_deep_dive_keys_are_not_required():
    """The 7 new Giai đoạn 4 keys must be optional (NotRequired)."""
    optional_keys = ResearchState.__optional_keys__
    for key in (
        "research_plan",
        "plan_approved",
        "scored_sources",
        "contradictions",
        "confidence_trace",
        "run_id",
        "headless",
    ):
        assert key in optional_keys, f"{key} must be NotRequired"


def test_existing_keys_still_required():
    """Pre-existing keys must remain required — no accidental widening."""
    required_keys = ResearchState.__required_keys__
    for key in (
        "query",
        "report_type",
        "source_urls",
        "agent",
        "agent_role",
        "sub_queries",
        "current_query_index",
        "search_results",
        "scraped_content",
        "context",
        "visited_urls",
        "report",
        "cfg",
        "websocket",
        "memory",
    ):
        assert key in required_keys, f"{key} must stay required"


def test_state_without_new_keys_is_still_valid_shape():
    """A state dict built the old way (no Giai đoạn 4 keys) must type-check
    the same as before — the schema change must be purely additive."""
    hints = get_type_hints(ResearchState, include_extras=True)
    assert "research_plan" in hints
    assert "plan_approved" in hints
    assert "scored_sources" in hints
    assert "contradictions" in hints
    assert "confidence_trace" in hints
    assert "run_id" in hints
    assert "headless" in hints
