"""Chunker protocol."""

from __future__ import annotations

from typing import Protocol


class Chunker(Protocol):
    """Text chunker interface."""

    def chunk(self, text: str) -> list[str]:
        """Split text into chunks."""

