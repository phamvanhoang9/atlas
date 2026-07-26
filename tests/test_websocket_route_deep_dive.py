"""Tests for the Giai đoạn 4 /ws restructuring: background-task job dispatch
plus plan_response routing, and the single-job-per-connection guard.
"""

import asyncio
import json

import pytest
from fastapi import WebSocketDisconnect

from src.api.routes import websocket as ws_route


class _FakeClient:
    host = "test-client"


class _ScriptedWebSocket:
    """Feeds a scripted sequence of incoming text messages, then disconnects."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self.client = _FakeClient()
        self.sent: list[dict] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        if not self._messages:
            raise WebSocketDisconnect()
        return self._messages.pop(0)

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


class _FakeManager:
    def __init__(self) -> None:
        self.running_jobs: set = set()
        self.resolved_plan_responses: list[tuple] = []
        self.suggested_questions: dict = {}
        self.evaluation_results: dict = {}
        self.sources: dict = {}
        self.start_streaming_calls: list[tuple] = []

    async def connect(self, websocket) -> None:
        pass

    async def disconnect(self, websocket) -> None:
        self.running_jobs.discard(websocket)

    def start_job(self, websocket) -> bool:
        if websocket in self.running_jobs:
            return False
        self.running_jobs.add(websocket)
        return True

    def finish_job(self, websocket) -> None:
        self.running_jobs.discard(websocket)

    def resolve_plan_response(self, websocket, run_id, payload) -> None:
        self.resolved_plan_responses.append((websocket, run_id, payload))

    async def start_streaming(self, task, report_type, websocket, run_id=""):
        self.start_streaming_calls.append((task, report_type, run_id))
        return "a finished report " * 20  # long enough to look real


@pytest.fixture(autouse=True)
def _patch_deps(monkeypatch):
    fake_manager = _FakeManager()
    monkeypatch.setattr(ws_route.deps, "manager", fake_manager)

    async def _run_sync(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ws_route.deps, "run_sync", _run_sync)

    fake_history = type(
        "FakeHistory",
        (),
        {
            "add_entry": staticmethod(lambda *a, **k: "hist-1"),
            "update_entry": staticmethod(lambda *a, **k: None),
        },
    )()
    monkeypatch.setattr(ws_route.deps, "history_manager", fake_history)

    async def _fake_auth(websocket):
        return True

    monkeypatch.setattr(ws_route, "require_websocket_auth", _fake_auth)

    async def _fake_pdf_export(report):
        return "/exports/report.pdf"

    monkeypatch.setattr(ws_route, "write_md_to_pdf", _fake_pdf_export)

    return fake_manager


@pytest.mark.asyncio
async def test_plan_response_dispatches_to_manager_with_run_id(_patch_deps):
    payload = {"run_id": "run-abc", "action": "approve"}
    ws = _ScriptedWebSocket([f"plan_response {json.dumps(payload)}"])

    await ws_route.websocket_endpoint(ws)

    assert _patch_deps.resolved_plan_responses == [(ws, "run-abc", payload)]
    # plan_response must never be treated as a job-start message.
    assert _patch_deps.start_streaming_calls == []


@pytest.mark.asyncio
async def test_second_start_while_job_running_is_rejected(_patch_deps):
    start_msg = json.dumps({"task": "t", "report_type": "ask"})
    ws = _ScriptedWebSocket([f"start {start_msg}", f"start {start_msg}"])

    await ws_route.websocket_endpoint(ws)
    # let the (only) spawned background job task run to completion
    await asyncio.sleep(0.05)

    errors = [m for m in ws.sent if m.get("type") == "error"]
    assert len(errors) == 1
    assert "already running" in errors[0]["output"]
    # only the first start actually reached start_streaming
    assert len(_patch_deps.start_streaming_calls) == 1


@pytest.mark.asyncio
async def test_start_does_not_block_the_receive_loop(_patch_deps):
    """The receive loop must keep accepting messages while a job runs in
    the background — this is what makes plan_response reachable at all."""
    start_msg = json.dumps({"task": "t", "report_type": "ask"})
    plan_payload = {"run_id": "run-xyz", "action": "approve"}
    ws = _ScriptedWebSocket([f"start {start_msg}", f"plan_response {json.dumps(plan_payload)}"])

    await ws_route.websocket_endpoint(ws)
    await asyncio.sleep(0.05)

    assert _patch_deps.resolved_plan_responses == [(ws, "run-xyz", plan_payload)]
