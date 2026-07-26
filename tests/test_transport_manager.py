"""Tests for `WebSocketManager` message caching in `src.transport.manager`."""

import asyncio
from unittest.mock import patch

from src.transport.manager import WebSocketManager, _WebsocketWrapper, run_agent


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


# ---------------------------------------------------------------------------
# Giai đoạn 4: plan-approval waiters (correlation, timeout, disconnect)
# ---------------------------------------------------------------------------


def test_plan_response_resolves_matching_waiter() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()

    async def _scenario():
        wait_task = asyncio.create_task(manager.await_plan_response(raw_ws, "run-1", timeout=5))
        await asyncio.sleep(0)  # let the waiter register itself
        manager.resolve_plan_response(raw_ws, "run-1", {"action": "approve"})
        return await wait_task

    result = asyncio.run(_scenario())
    assert result == {"action": "approve"}


def test_plan_response_does_not_cross_resolve_different_run_ids() -> None:
    """A stale/duplicate response for an old run_id must not resolve a new job's wait."""
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()

    async def _scenario():
        wait_task = asyncio.create_task(manager.await_plan_response(raw_ws, "run-2", timeout=0.3))
        await asyncio.sleep(0)
        manager.resolve_plan_response(raw_ws, "run-1-stale", {"action": "approve"})
        return await wait_task

    result = asyncio.run(_scenario())
    assert result == {"action": "_timeout_or_disconnected"}


def test_resolve_plan_response_with_no_pending_waiter_is_a_safe_noop() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()
    manager.resolve_plan_response(raw_ws, "no-such-run", {"action": "approve"})  # must not raise


def test_await_plan_response_times_out_to_sentinel_not_exception() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()

    result = asyncio.run(manager.await_plan_response(raw_ws, "run-3", timeout=0.05))

    assert result == {"action": "_timeout_or_disconnected"}


def test_disconnect_cancels_pending_plan_waiter_to_sentinel_not_exception() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()

    async def _scenario():
        await manager.connect(raw_ws)
        wait_task = asyncio.create_task(manager.await_plan_response(raw_ws, "run-4", timeout=30))
        await asyncio.sleep(0)
        await manager.disconnect(raw_ws)
        return await wait_task

    result = asyncio.run(_scenario())
    assert result == {"action": "_timeout_or_disconnected"}


def test_plan_waiters_cleared_after_resolution() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()

    async def _scenario():
        wait_task = asyncio.create_task(manager.await_plan_response(raw_ws, "run-5", timeout=5))
        await asyncio.sleep(0)
        manager.resolve_plan_response(raw_ws, "run-5", {"action": "reject"})
        await wait_task

    asyncio.run(_scenario())
    assert (raw_ws, "run-5") not in manager.plan_waiters


# ---------------------------------------------------------------------------
# Giai đoạn 4: single-job-per-connection guard
# ---------------------------------------------------------------------------


def test_start_job_returns_true_when_no_job_running() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()
    assert manager.start_job(raw_ws) is True


def test_start_job_returns_false_when_already_running() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()
    manager.start_job(raw_ws)
    assert manager.start_job(raw_ws) is False


def test_finish_job_allows_a_new_job_to_start() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()
    manager.start_job(raw_ws)
    manager.finish_job(raw_ws)
    assert manager.start_job(raw_ws) is True


def test_wrapper_await_plan_response_delegates_to_manager() -> None:
    manager = WebSocketManager()
    raw_ws = _FakeWebSocket()
    wrapper = _WebsocketWrapper(raw_ws, manager, raw_ws)

    async def _scenario():
        wait_task = asyncio.create_task(wrapper.await_plan_response("run-9", timeout=5))
        await asyncio.sleep(0)
        manager.resolve_plan_response(raw_ws, "run-9", {"action": "approve"})
        return await wait_task

    result = asyncio.run(_scenario())
    assert result == {"action": "approve"}


def test_wrapper_await_plan_response_without_manager_fails_closed() -> None:
    """A wrapper built without a manager (defensive default) must not hang or crash."""
    raw_ws = _FakeWebSocket()
    wrapper = _WebsocketWrapper(raw_ws, None, raw_ws)

    result = asyncio.run(wrapper.await_plan_response("run-10", timeout=5))
    assert result == {"action": "_timeout_or_disconnected"}


class _AcceptingFakeWebSocket(_FakeWebSocket):
    async def receive_text(self):  # pragma: no cover - not exercised here
        raise NotImplementedError


def test_run_agent_threads_run_id_into_researcher() -> None:
    raw_ws = _AcceptingFakeWebSocket()
    manager = WebSocketManager()

    captured = {}

    class _FakeResearcher:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def run(self):
            return "report text"

    with patch("src.orchestration.runner.LangGraphResearcher", _FakeResearcher):
        asyncio.run(run_agent("task", "deep_dive", raw_ws, manager, run_id="run-42"))

    assert captured["run_id"] == "run-42"
    assert captured["headless"] is False
