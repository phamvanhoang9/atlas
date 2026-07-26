"""The approved Deep Dive plan must actually steer sub-query generation,
not just decorate the final report (doubt-driven-development finding:
a plan gate that doesn't influence search isn't "agentic")."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.planner import generate_sub_queries_node
from src.prompts.functions import generate_search_queries_prompt


def test_prompt_includes_plan_headings_when_present():
    prompt = generate_search_queries_prompt(
        "test topic",
        max_iterations=3,
        mode="deep_dive",
        research_plan={"headings": ["Heading A", "Heading B"], "approach": "x"},
    )
    assert "Heading A" in prompt
    assert "Heading B" in prompt


def test_prompt_omits_plan_block_when_absent():
    prompt = generate_search_queries_prompt("test topic", max_iterations=3, mode="ask")
    assert "Heading A" not in prompt


@pytest.mark.asyncio
async def test_generate_sub_queries_node_threads_plan_from_state():
    state = {
        "query": "test topic",
        "report_type": "deep_dive",
        "research_plan": {"headings": ["Heading A"], "approach": "x"},
        "cfg": MagicMock(max_iterations=2, temperature=0.2, llm_provider="openai", llm_kwargs={}),
        "websocket": None,
    }

    captured_prompt = {}

    async def _fake_completion(**kwargs):
        captured_prompt["content"] = kwargs["messages"][1]["content"]
        return '["query 1", "query 2"]'

    with patch("src.agents.planner.create_chat_completion", new=AsyncMock(side_effect=_fake_completion)):
        await generate_sub_queries_node(state)

    assert "Heading A" in captured_prompt["content"]
