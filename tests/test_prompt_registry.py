from src.prompts.functions import (
    auto_agent_instructions,
    generate_search_queries_prompt,
    get_report_by_type,
)


def test_search_query_prompt_uses_yaml_template() -> None:
    prompt = generate_search_queries_prompt("agentic AI production", max_iterations=2)

    assert "Generate exactly 2 web search queries" in prompt
    assert "valid JSON array" in prompt
    assert "agentic AI production" in prompt


def test_search_query_prompt_applies_mode_policy() -> None:
    quick = generate_search_queries_prompt("agentic AI production", max_iterations=2, mode="quick")
    research = generate_search_queries_prompt("agentic AI production", max_iterations=2, mode="research")

    assert "Do NOT" in quick and "restrict to academic papers" in quick
    assert "site:arxiv.org" in research


def test_report_prompt_uses_yaml_template() -> None:
    prompt = get_report_by_type("quick")(
        "What is reranking?",
        ["Source: https://example.com\nContent: reranking improves relevance"],
        "markdown",
        1000,
    )

    assert "User question:" in prompt
    assert "https://example.com" in prompt
    assert "Place [N] at the END of" in prompt
    assert "## Sources" in prompt


def test_report_prompt_falls_back_for_unknown_mode_string() -> None:
    unknown = get_report_by_type("hỏi đáp")("q", ["ctx"], "markdown", 500)
    research = get_report_by_type("research")("q", ["ctx"], "markdown", 500)

    assert unknown == research


def test_deep_mode_with_urls_uses_source_analysis_template() -> None:
    prompt = get_report_by_type("deep", has_source_urls=True)("q", ["ctx"], "markdown", 500)

    assert "explaining the provided source documents" in prompt


def test_agent_prompt_uses_yaml_template() -> None:
    prompt = auto_agent_instructions()

    assert "Return only valid JSON" in prompt
    assert "agent_role_prompt" in prompt
