"""Tests for the 'sources' WebSocket message built by `_filter_academic`."""

import pytest

from src.agents.searcher import _filter_academic


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_sources_message_includes_snippet_for_explain_button() -> None:
    """The Explain button (Phần 1 #2) needs a short passage per source to
    send to /api/explain; derive it from the scraped raw_content."""
    ws = _FakeWebSocket()
    scraped = [
        {
            "url": "https://arxiv.org/abs/1234",
            "title": "A Paper",
            "raw_content": "A" * 500,
        }
    ]

    await _filter_academic(scraped, ws)

    sources_messages = [m for m in ws.sent if m["type"] == "sources"]
    assert len(sources_messages) == 1
    source = sources_messages[0]["output"][0]
    assert source["snippet"] == "A" * 280
    assert len(source["snippet"]) <= 280


@pytest.mark.asyncio
async def test_sources_message_handles_missing_raw_content() -> None:
    ws = _FakeWebSocket()
    scraped = [{"url": "https://example.com", "title": "T", "raw_content": "short but present text ok"}]

    await _filter_academic(scraped, ws)

    sources_messages = [m for m in ws.sent if m["type"] == "sources"]
    source = sources_messages[0]["output"][0]
    assert source["snippet"] == "short but present text ok"
