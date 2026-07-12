"""Tests for the YAML-templated prompt registry: search query, report, and agent prompts."""

from src.prompts.functions import (
    auto_agent_instructions,
    generate_scope_gate_prompt,
    generate_search_queries_prompt,
    get_report_by_type,
)


def test_search_query_prompt_uses_yaml_template() -> None:
    prompt = generate_search_queries_prompt("agentic AI production", max_iterations=2)

    assert "Generate exactly 2 web search queries" in prompt
    assert "valid JSON array" in prompt
    assert "agentic AI production" in prompt


def test_search_query_prompt_applies_mode_policy() -> None:
    quick = generate_search_queries_prompt("agentic AI production", max_iterations=2, mode="ask")
    research = generate_search_queries_prompt("agentic AI production", max_iterations=2, mode="compare")

    assert "Do NOT" in quick and "restrict to academic papers" in quick
    assert "site:arxiv.org" in research


def test_report_prompt_uses_yaml_template() -> None:
    prompt = get_report_by_type("ask")(
        "What is reranking?",
        ["Source: https://example.com\nContent: reranking improves relevance"],
        "markdown",
        1000,
    )

    assert "User question:" in prompt
    assert "https://example.com" in prompt
    assert "Place [N] at the END of" in prompt
    assert "## Sources" in prompt


def test_ask_prompt_is_an_answer_card_with_one_claim_and_one_caveat() -> None:
    """Ask output is an Answer Card (modes_redesign_plan.md Mục 4 Mode 1):
    ONE core claim + ONE caveat, not a multi-bullet report. The trust badge
    itself is computed deterministically by the frontend from source_scorer
    categories, never by the LLM — the prompt must not ask the model to
    invent a trust score."""
    prompt = get_report_by_type("ask")(
        "What is reranking?",
        ["Source: https://example.com\nContent: reranking improves relevance"],
        "markdown",
        200,
    )

    assert "## Answer" in prompt
    assert "## Caveat" in prompt
    assert "## Evidence" not in prompt
    assert "## Caveats" not in prompt
    assert "ONE" in prompt
    assert "trust" not in prompt.lower()


def test_report_prompt_falls_back_for_unknown_mode_string() -> None:
    unknown = get_report_by_type("hỏi đáp")("q", ["ctx"], "markdown", 500)
    research = get_report_by_type("compare")("q", ["ctx"], "markdown", 500)

    assert unknown == research


def test_deep_mode_with_urls_uses_source_analysis_template() -> None:
    prompt = get_report_by_type("deep_dive", has_source_urls=True)("q", ["ctx"], "markdown", 500)

    assert "explaining the provided source documents" in prompt


def test_agent_prompt_uses_yaml_template() -> None:
    prompt = auto_agent_instructions()

    assert "Return only valid JSON" in prompt
    assert "agent_role_prompt" in prompt


def test_scope_gate_prompt_defaults_to_ai_native_soft_wording() -> None:
    default_prompt = generate_scope_gate_prompt("some query")
    explicit_native = generate_scope_gate_prompt("some query", scope_mode="ai_native")

    assert default_prompt == explicit_native
    assert "Default to IN SCOPE" in default_prompt


def test_scope_gate_prompt_ai_strict_requires_ai_central() -> None:
    prompt = generate_scope_gate_prompt("some query", scope_mode="ai_strict")

    assert "central" in prompt
    assert "Default to IN SCOPE" not in prompt


def test_scope_gate_prompt_unknown_mode_falls_back_to_ai_native() -> None:
    prompt = generate_scope_gate_prompt("some query", scope_mode="not_a_real_mode")

    assert "Default to IN SCOPE" in prompt
