"""Semantic retrieval placeholder for persistent vector search."""

from __future__ import annotations


class SemanticRetriever:
    """Minimal interface reserved for vector retrieval integration."""

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Return semantic matches. Persistent vector backend is not configured yet."""
        return []

