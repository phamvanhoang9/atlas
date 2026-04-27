"""Base protocol for agent nodes."""

from __future__ import annotations

from typing import Any, Protocol

from src.orchestration.state import ResearchState


class AgentNode(Protocol):
    """Async LangGraph-compatible node."""

    async def __call__(self, state: ResearchState) -> dict[str, Any]:
        """Execute the node and return a state update."""

