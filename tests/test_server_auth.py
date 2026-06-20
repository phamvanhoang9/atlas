"""Tests for HTTP/WebSocket auth gating and a full sample research flow over `/ws`."""

from fastapi.testclient import TestClient
from pathlib import Path
from uuid import uuid4

import src.api.app as server
from src.api import deps
from src.api.routes import websocket as websocket_route
from src.storage.history import SQLiteHistoryManager


app = server.app


class FakeWebSocketManager:
    """Stand-in for `transport.manager` that streams canned messages instead of researching."""

    def __init__(self) -> None:
        self.suggested_questions = {}

    async def connect(self, websocket) -> None:
        await websocket.accept()
        self.suggested_questions[websocket] = ["Câu hỏi mẫu?"]

    async def disconnect(self, websocket) -> None:
        self.suggested_questions.pop(websocket, None)

    async def start_streaming(self, task: str, report_type: str, websocket) -> str:
        await websocket.send_json({"type": "logs", "output": "Đang chạy kiểm thử mẫu..."})
        await websocket.send_json({"type": "report", "output": "# Báo cáo mẫu\nNội dung mẫu."})
        return "# Báo cáo mẫu\nNội dung mẫu."


def test_history_api_allows_requests_when_auth_disabled(monkeypatch):
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)
    client = TestClient(app)

    response = client.get("/api/history")

    assert response.status_code == 200


def test_history_api_rejects_requests_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("ATLAS_AUTH_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.get("/api/history")

    assert response.status_code == 401


def test_history_api_accepts_bearer_token(monkeypatch):
    monkeypatch.setenv("ATLAS_AUTH_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.get("/api/history", headers={"Authorization": "Bearer secret-token"})

    assert response.status_code == 200


def test_history_api_accepts_query_token(monkeypatch):
    monkeypatch.setenv("ATLAS_AUTH_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.get("/api/history?token=secret-token")

    assert response.status_code == 200


def test_websocket_user_flow_sample_without_external_api(monkeypatch):
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)
    history_file = Path(".atlas_cache") / f"test_history_{uuid4().hex}.sqlite"
    fake_manager = FakeWebSocketManager()
    monkeypatch.setattr(deps, "manager", fake_manager)
    monkeypatch.setattr(deps, "history_manager", SQLiteHistoryManager(str(history_file)))

    async def fake_write_md_to_pdf(report: str) -> str:
        return "outputs/sample.pdf"

    monkeypatch.setattr(websocket_route, "write_md_to_pdf", fake_write_md_to_pdf)
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.send_text('start {"task": "Transformer là gì?", "report_type": "quick"}')
        first = websocket.receive_json()
        second = websocket.receive_json()
        third = websocket.receive_json()
        fourth = websocket.receive_json()

    assert first["type"] == "history_id"
    assert second == {"type": "logs", "output": "Đang chạy kiểm thử mẫu..."}
    assert third["type"] == "report"
    assert fourth == {"type": "path", "output": "outputs/sample.pdf"}
