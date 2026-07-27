"""Tests for the 'sources' WebSocket message built by `_filter_academic`."""

import pytest

from src.agents.searcher import _filter_academic


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


@pytest.mark.asyncio
async def test_sources_message_has_no_snippet_field() -> None:
    """The per-source Explain button (and its `snippet` payload) was removed
    in favor of highlight-to-explain on the report text itself — the
    'sources' message must not carry a snippet anymore."""
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
    assert "snippet" not in source
