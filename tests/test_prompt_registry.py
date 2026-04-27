from src.prompts.functions import (
    auto_agent_instructions,
    generate_search_queries_prompt,
    get_report_by_type,
)


def test_search_query_prompt_uses_yaml_template() -> None:
    prompt = generate_search_queries_prompt("agentic AI production", max_iterations=2)

    assert "Generate exactly 2 academic search queries" in prompt
    assert "valid JSON array" in prompt
    assert "agentic AI production" in prompt


def test_report_prompt_uses_yaml_template() -> None:
    prompt = get_report_by_type("hỏi đáp")(
        "What is reranking?",
        ["Source: https://example.com\nContent: reranking improves relevance"],
        "markdown",
        1000,
    )

    assert "User question:" in prompt
    assert "https://example.com" in prompt
    assert "Cite sources inline" in prompt


def test_agent_prompt_uses_yaml_template() -> None:
    prompt = auto_agent_instructions()

    assert "Return only valid JSON" in prompt
    assert "agent_role_prompt" in prompt
