"""Tests for plan_gate_node and contradiction_check_node (Giai đoạn 4).

Covers the edge cases locked during doubt-driven-development review:
headless auto-approve (with belt-and-suspenders fallback), interactive
approve/reject/regenerate, revision cap, fail-closed on timeout/disconnect
sentinel and on unknown actions, fail-open plan generation, and
contradiction_check's deterministic scoring / empty-context / unmatched-URL
handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.deep_dive import contradiction_check_node, plan_gate_node


def _cfg(**overrides):
    cfg = MagicMock()
    cfg.llm_model = "gpt-4o"
    cfg.llm_provider = "openai"
    cfg.temperature = 0.2
    cfg.llm_kwargs = {}
    cfg.plan_approval_timeout_seconds = 600
    cfg.max_plan_revisions = 3
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _base_state(**overrides):
    state = {
        "query": "test query",
        "report_type": "deep_dive",
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
        "cfg": _cfg(),
        "websocket": None,
        "memory": MagicMock(),
        "run_id": "run-1",
    }
    state.update(overrides)
    return state


_PLAN_JSON = '{"headings": ["A", "B"], "approach": "do the thing"}'


class _FakeInteractiveWS:
    """Fake websocket exposing await_plan_response, scripted with responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent: list[dict] = []
        self.wait_calls: list[tuple] = []

    async def send_json(self, data):
        self.sent.append(data)

    async def await_plan_response(self, run_id, timeout):
        self.wait_calls.append((run_id, timeout))
        return self._responses.pop(0)


# --------------------------------------------------------------------------
# plan_gate_node
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_headless_auto_approves_without_waiting():
    state = _base_state(headless=True, websocket=_FakeInteractiveWS([{"action": "approve"}]))

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=_PLAN_JSON):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is True
    assert result["research_plan"]["headings"] == ["A", "B"]
    assert state["websocket"].wait_calls == []  # never waited


@pytest.mark.asyncio
async def test_belt_and_suspenders_auto_approves_when_headless_unset_but_ws_cannot_wait():
    """Guards against a caller forgetting headless=True (e.g. CapturingWebSocket)."""
    # Models CapturingWebSocket's real shape: has send_json, no await_plan_response.
    state = _base_state(headless=False, websocket=MagicMock(spec=["send_json"]))
    state["websocket"].send_json = AsyncMock()

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=_PLAN_JSON):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is True


@pytest.mark.asyncio
async def test_interactive_approve():
    ws = _FakeInteractiveWS([{"action": "approve"}])
    state = _base_state(websocket=ws)

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=_PLAN_JSON):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is True
    assert result["research_plan"]["headings"] == ["A", "B"]


@pytest.mark.asyncio
async def test_interactive_approve_with_edited_plan():
    edited = {"action": "approve", "plan": {"headings": ["Edited heading"], "approach": "edited approach"}}
    ws = _FakeInteractiveWS([edited])
    state = _base_state(websocket=ws)

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=_PLAN_JSON):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is True
    assert result["research_plan"]["headings"] == ["Edited heading"]
    assert result["research_plan"]["approach"] == "edited approach"


@pytest.mark.asyncio
async def test_interactive_reject_cancels_with_report():
    ws = _FakeInteractiveWS([{"action": "reject"}])
    state = _base_state(websocket=ws)

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=_PLAN_JSON):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is False
    assert result["report"]  # non-empty cancellation message
    assert "test query" in result["report"] or len(result["report"]) > 0


@pytest.mark.asyncio
async def test_timeout_or_disconnect_sentinel_fails_closed():
    ws = _FakeInteractiveWS([{"action": "_timeout_or_disconnected"}])
    state = _base_state(websocket=ws)

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=_PLAN_JSON):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is False
    assert result["report"]


@pytest.mark.asyncio
async def test_unknown_action_fails_closed():
    ws = _FakeInteractiveWS([{"action": "something_unexpected"}])
    state = _base_state(websocket=ws)

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=_PLAN_JSON):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is False


@pytest.mark.asyncio
async def test_regenerate_then_approve_calls_llm_twice():
    ws = _FakeInteractiveWS([
        {"action": "regenerate", "feedback": "different focus"},
        {"action": "approve"},
    ])
    state = _base_state(websocket=ws)

    llm = AsyncMock(return_value=_PLAN_JSON)
    with patch("src.agents.deep_dive.create_chat_completion", llm):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is True
    assert llm.call_count == 2
    assert len(ws.wait_calls) == 2


@pytest.mark.asyncio
async def test_revision_cap_auto_approves_last_shown_plan_without_new_llm_call():
    cfg = _cfg(max_plan_revisions=1)
    # 1 regenerate is allowed (revision 0 -> 1); the 2nd regenerate request
    # exceeds the cap and must auto-approve WITHOUT generating a 3rd plan.
    ws = _FakeInteractiveWS([
        {"action": "regenerate"},
        {"action": "regenerate"},
    ])
    state = _base_state(websocket=ws, cfg=cfg)

    llm = AsyncMock(return_value=_PLAN_JSON)
    with patch("src.agents.deep_dive.create_chat_completion", llm):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is True
    # initial plan + 1 allowed regenerate = 2 LLM calls, not 3
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_initial_plan_generation_failure_falls_back_to_default_plan():
    ws = _FakeInteractiveWS([{"action": "approve"}])
    state = _base_state(websocket=ws)

    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        result = await plan_gate_node(state)

    assert result["plan_approved"] is True
    assert len(result["research_plan"]["headings"]) > 0


# --------------------------------------------------------------------------
# contradiction_check_node
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_scored_sources_skips_llm_call_and_reports_low_confidence():
    state = _base_state(scored_sources=[])

    llm = AsyncMock()
    with patch("src.agents.deep_dive.create_chat_completion", llm):
        result = await contradiction_check_node(state)

    assert result["contradictions"] == []
    assert result["confidence_trace"]["label"] == "Low"
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_contradiction_entries_joined_to_scored_sources():
    scored_sources = [
        {"url": "https://a.example/paper", "source_category": "peer_reviewed", "quality_score": 90},
        {"url": "https://b.example/blog", "source_category": "engineering_blog", "quality_score": 60},
    ]
    state = _base_state(scored_sources=scored_sources, context=["some context"])

    llm_json = (
        '[{"type": "cross_source", "topic": "latency claim", "entries": '
        '[{"source_url": "https://a.example/paper", "claim": "X is fast"}, '
        '{"source_url": "https://b.example/blog", "claim": "X is slow"}]}]'
    )
    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=llm_json):
        result = await contradiction_check_node(state)

    assert len(result["contradictions"]) == 1
    entry = result["contradictions"][0]
    assert entry["type"] == "cross_source"
    sources_by_url = {e["source_url"]: e for e in entry["entries"]}
    assert sources_by_url["https://a.example/paper"]["quality_score"] == 90
    assert sources_by_url["https://a.example/paper"]["source_category"] == "peer_reviewed"
    assert sources_by_url["https://b.example/blog"]["quality_score"] == 60
    assert result["confidence_trace"]["label"] in ("High", "Medium", "Low")


@pytest.mark.asyncio
async def test_llm_failure_fails_open_but_confidence_trace_still_computed():
    scored_sources = [{"url": "https://a.example", "source_category": "official", "quality_score": 95}]
    state = _base_state(scored_sources=scored_sources, context=["ctx"])

    with patch(
        "src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, side_effect=RuntimeError("boom")
    ):
        result = await contradiction_check_node(state)

    assert result["contradictions"] == []
    assert result["confidence_trace"]["label"] == "High"


@pytest.mark.asyncio
async def test_malformed_json_fails_open():
    scored_sources = [{"url": "https://a.example", "source_category": "official", "quality_score": 95}]
    state = _base_state(scored_sources=scored_sources, context=["ctx"])

    with patch(
        "src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value="not json at all"
    ):
        result = await contradiction_check_node(state)

    assert result["contradictions"] == []


@pytest.mark.asyncio
async def test_hallucinated_source_url_does_not_crash():
    scored_sources = [{"url": "https://a.example", "source_category": "official", "quality_score": 95}]
    state = _base_state(scored_sources=scored_sources, context=["ctx"])

    llm_json = (
        '[{"type": "internal", "topic": "t", "entries": '
        '[{"source_url": "https://never-seen.example/x", "claim": "made up"}]}]'
    )
    with patch("src.agents.deep_dive.create_chat_completion", new_callable=AsyncMock, return_value=llm_json):
        result = await contradiction_check_node(state)

    assert len(result["contradictions"]) == 1
    entry = result["contradictions"][0]["entries"][0]
    assert entry["source_url"] == "https://never-seen.example/x"
    assert entry["quality_score"] is None
