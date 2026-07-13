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


def test_compare_uses_decision_matrix_template() -> None:
    """Compare's job is a structured comparison, not the old free-form
    'research_report' essay - see modes_redesign_plan.md Mục 7 Giai đoạn 2."""
    prompt = get_report_by_type("compare")(
        "GPT-4o vs Claude vs Gemini for Vietnamese summarization",
        ["Source: https://example.com\nContent: benchmark results"],
        "markdown",
        1200,
    )

    assert "## Objects Compared" in prompt
    assert "## Decision Matrix" in prompt
    assert "## Implementation & Benchmarks" in prompt
    assert "## Recommendation" in prompt
    assert "## Trade-offs" not in prompt  # old research_report heading, retired


def test_compare_decision_matrix_covers_mandatory_edge_cases() -> None:
    """Doubt-driven-development requires these edge cases (Mục 8.2) to be
    explicitly instructed, not left to happy-path chance: single object,
    >5 objects, alias merging, and no-evidence cells."""
    prompt = get_report_by_type("compare")("q", ["ctx"], "markdown", 500)

    assert "ONE clear object" in prompt
    assert "more than 5 distinct objects" in prompt
    assert "SAME underlying" in prompt
    assert "No evidence found" in prompt


def test_compare_url_mode_also_uses_decision_matrix_template() -> None:
    prompt = get_report_by_type("compare", has_source_urls=True)("q", ["ctx"], "markdown", 500)

    assert "## Decision Matrix" in prompt


def test_compare_prompt_instructs_light_contradiction_flagging() -> None:
    """Light contradiction (Mục 7 Giai đoạn 2 #3) lives at the prompt/output
    level for now - no new LangGraph node until the full contradiction_check
    is built in Giai đoạn 4. Must never let the model silently pick a side."""
    prompt = get_report_by_type("compare")("q", ["ctx"], "markdown", 500)

    assert "## Contradictions" in prompt
    assert "do not silently pick" in prompt


def test_compare_prompt_instructs_paper_code_benchmark_linking() -> None:
    """Paper<->code<->benchmark linking (Mục 2, Papers with Code gap) uses
    the source_scorer category label already present in each source header
    (context_builder.py's `category_line`) - never invents a repo/benchmark
    link the context doesn't actually provide."""
    prompt = get_report_by_type("compare")("q", ["ctx"], "markdown", 500)

    assert "## Implementation & Benchmarks" in prompt
    assert "do not invent a repo or benchmark link" in prompt


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
