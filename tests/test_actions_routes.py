"""Route-level tests for /api/explain and /api/vet (HTTP layer only — the
business logic itself is covered by tests/test_actions.py)."""

from fastapi.testclient import TestClient

import src.api.app as server

app = server.app


def test_explain_route_skips_llm_for_short_passage(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)

    async def _fail(**kwargs):
        raise AssertionError("LLM must not be called for a too-short passage")

    monkeypatch.setattr("src.actions.explain.create_chat_completion", _fail)
    client = TestClient(app)

    response = client.post("/api/explain", json={"passage": "ok"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["skipped"] is True
    assert body["data"]["reason"] == "too_short"


def test_explain_route_returns_explanation(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)

    async def _fake(**kwargs):
        return "A plain-language explanation."

    monkeypatch.setattr("src.actions.explain.create_chat_completion", _fake)
    client = TestClient(app)

    response = client.post(
        "/api/explain", json={"passage": "Speculative decoding drafts tokens with a small model."}
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["skipped"] is False
    assert body["explanation"] == "A plain-language explanation."


def test_actions_routes_require_auth_when_token_configured(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_AUTH_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.post("/api/explain", json={"passage": "some passage text here"})

    assert response.status_code == 401
