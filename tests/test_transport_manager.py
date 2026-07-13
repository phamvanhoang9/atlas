"""Tests for `WebSocketManager` message caching in `src.transport.manager`."""

import asyncio

from src.transport.manager import WebSocketManager, _WebsocketWrapper


class _FakeWebSocket:
    """Minimal stand-in that only implements `send_json`, as required by `_WebsocketWrapper`."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def accept(self) -> None:
        pass

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


def test_wrapper_caches_sources_message_for_history_persistence() -> None:
    """The 'sources' WebSocket message must be cached on the manager (like
    suggested_questions/evaluation already are) so the websocket route can
    persist it via `history_manager.update_entry(sources=...)` once the
    report finishes — see modes_redesign_plan.md Phần 1 #1."""
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()
    wrapper = _WebsocketWrapper(raw_ws, manager, raw_ws)

    payload = [{"url": "https://arxiv.org/abs/1", "title": "Paper", "category": "arxiv_preprint", "score": 82}]
    asyncio.run(wrapper.send_json({"type": "sources", "output": payload}))

    assert manager.sources.get(raw_ws) == payload
    assert raw_ws.sent == [{"type": "sources", "output": payload}]


def test_wrapper_ignores_sources_message_with_non_list_output() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()
    wrapper = _WebsocketWrapper(raw_ws, manager, raw_ws)

    asyncio.run(wrapper.send_json({"type": "sources", "output": "not-a-list"}))

    assert raw_ws not in manager.sources


def test_disconnect_clears_cached_sources() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()

    async def _scenario() -> None:
        await manager.connect(raw_ws)
        manager.sources[raw_ws] = [{"url": "https://example.com"}]
        await manager.disconnect(raw_ws)

    asyncio.run(_scenario())

    assert raw_ws not in manager.sources
