"""Tests for the AI-domain scope gate node and its workflow routing."""

from types import SimpleNamespace

import pytest

from src.agents.scope_gate import (
    _query_matches_ai_keywords,
    build_refusal_report,
    scope_gate_node,
)
from src.orchestration.router import route_after_scope_gate


def _state(query: str, **overrides) -> dict:
    """Build a minimal `ResearchState`-shaped dict for the given query.

    Args:
      query: The user query to embed in the state.
      **overrides: Additional state keys to set or override on top of the
        defaults.

    Returns:
      A dict with the state keys `scope_gate_node` and routing functions
      depend on.
    """
    cfg = SimpleNamespace(
        llm_model="test-model",
        llm_provider="openai",
        llm_kwargs={},
        temperature=0.0,
        scope_mode="ai_native",
    )
    state = {
        "query": query,
        "report_type": "ask",
        "source_urls": [],
        "agent": "",
        "agent_role": "",
        "sub_queries": [],
        "current_query_index": 0,
        "search_results": [],
        "scraped_content": [],
        "context": [],
        "visited_urls": [],
        "report": "",
        "cfg": cfg,
        "websocket": None,
        "memory": None,
    }
    state.update(overrides)
    return state


def test_ai_keyword_fast_path_accepts_obvious_queries() -> None:
    assert _query_matches_ai_keywords("How does RAG chunking affect retrieval quality?")
    assert _query_matches_ai_keywords("Compare GPT-4o and Claude for coding")
    assert _query_matches_ai_keywords("fine-tuning LLaMA on legal data")
    assert _query_matches_ai_keywords("Mô hình ngôn ngữ lớn cho tiếng Việt")


def test_ai_keyword_fast_path_rejects_non_ai_queries() -> None:
    assert not _query_matches_ai_keywords("best pizza in Hanoi")
    assert not _query_matches_ai_keywords("how to grow tomatoes at home")


@pytest.mark.asyncio
async def test_scope_gate_fast_path_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fail(**kwargs):
        raise AssertionError("LLM must not be called on the fast path")

    monkeypatch.setattr("src.agents.scope_gate.create_chat_completion", _fail)

    result = await scope_gate_node(_state("What is a transformer attention head?"))

    assert result["scope_refusal"] is False


@pytest.mark.asyncio
async def test_scope_gate_refuses_out_of_scope_query(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(**kwargs):
        return (
            '{"in_scope": false, "reason": "cooking question", '
            '"suggested_reframe": "How are AI models used in recipe generation?"}'
        )

    monkeypatch.setattr("src.agents.scope_gate.create_chat_completion", _fake)

    result = await scope_gate_node(_state("best pizza in Hanoi"))

    assert result["scope_refusal"] is True
    assert "Out of scope" in result["report"]
    assert "How are AI models used in recipe generation?" in result["report"]
    assert route_after_scope_gate(result) == "refused"


@pytest.mark.asyncio
async def test_scope_gate_accepts_in_scope_llm_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(**kwargs):
        return '{"in_scope": true, "reason": "AI hardware question", "suggested_reframe": ""}'

    monkeypatch.setattr("src.agents.scope_gate.create_chat_completion", _fake)

    result = await scope_gate_node(_state("Which accelerators matter for serving workloads?"))

    assert result["scope_refusal"] is False
    assert route_after_scope_gate(result) == "in_scope"


@pytest.mark.asyncio
async def test_scope_gate_fails_open_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("src.agents.scope_gate.create_chat_completion", _boom)

    result = await scope_gate_node(_state("obscure question without ai words"))

    assert result["scope_refusal"] is False


@pytest.mark.asyncio
async def test_scope_gate_sends_refusal_over_websocket(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict] = []

        async def send_json(self, payload: dict) -> None:
            self.messages.append(payload)

    async def _fake(**kwargs):
        return '{"in_scope": false, "reason": "travel", "suggested_reframe": ""}'

    monkeypatch.setattr("src.agents.scope_gate.create_chat_completion", _fake)
    ws = FakeWebSocket()

    result = await scope_gate_node(_state("cheap flights to Tokyo", websocket=ws))

    types = [m.get("type") for m in ws.messages]
    assert "refusal" in types
    assert "report" in types
    assert result["scope_refusal"] is True


def test_refusal_report_without_reframe_suggests_ai_angle() -> None:
    report = build_refusal_report("best pizza in Hanoi")

    assert "Out of scope" in report
    assert "AI angle" in report


def test_route_after_scope_gate_defaults_to_in_scope() -> None:
    assert route_after_scope_gate({"query": "x"}) == "in_scope"


@pytest.mark.asyncio
async def test_scope_gate_passes_configured_scope_mode_to_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def _fake_prompt(query: str, scope_mode: str = "ai_native") -> str:
        captured["scope_mode"] = scope_mode
        return "PROMPT"

    async def _fake_completion(**kwargs):
        return '{"in_scope": true, "reason": "ok", "suggested_reframe": ""}'

    monkeypatch.setattr("src.agents.scope_gate.generate_scope_gate_prompt", _fake_prompt)
    monkeypatch.setattr("src.agents.scope_gate.create_chat_completion", _fake_completion)

    state = _state("best pizza in Hanoi")
    state["cfg"].scope_mode = "ai_strict"

    await scope_gate_node(state)

    assert captured["scope_mode"] == "ai_strict"
