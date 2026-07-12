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


def test_vet_route_rejects_blank_claim(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)
    client = TestClient(app)

    response = client.post("/api/vet", json={"claim": "   "})

    assert response.status_code == 400


def test_vet_route_returns_insufficient_evidence_when_nothing_found(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)

    class _EmptyRetriever:
        def __init__(self, query, include_domains=None):
            pass

        def search(self, max_results):
            return []

    async def _fail(**kwargs):
        raise AssertionError("LLM must not be called when no evidence was retrieved")

    monkeypatch.setattr("src.actions.vet.TavilySearch", _EmptyRetriever)
    monkeypatch.setattr("src.actions.vet.create_chat_completion", _fail)
    client = TestClient(app)

    response = client.post("/api/vet", json={"claim": "some claim with no evidence"})

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["verdict"] == "insufficient_evidence"
    assert body["evidence"] == []


def test_actions_routes_require_auth_when_token_configured(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_AUTH_TOKEN", "secret-token")
    client = TestClient(app)

    response = client.post("/api/explain", json={"passage": "some passage text here"})

    assert response.status_code == 401
