"""Recursive text chunker wrapper."""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter


class RecursiveChunker:
    """Fallback chunker for web content."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def chunk(self, text: str) -> list[str]:
        """Split text into recursive chunks."""
        return self.splitter.split_text(text or "")

