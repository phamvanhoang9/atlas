"""Structure-aware academic paper chunker."""

from __future__ import annotations

import re

from src.rag.chunking.recursive_chunker import RecursiveChunker


SECTION_PATTERN = re.compile(
    r"(?im)^\s*(abstract|introduction|related work|method|methods|methodology|experiments?|results?|discussion|conclusion|references)\s*$"
)


class PaperChunker:
    """Chunk academic papers by recognizable sections with recursive fallback."""

    def __init__(self, fallback_chunk_size: int = 1500, fallback_overlap: int = 200) -> None:
        self.fallback = RecursiveChunker(fallback_chunk_size, fallback_overlap)

    def chunk(self, text: str) -> list[str]:
        """Split a paper into section-aware chunks."""
        if not text:
            return []

        matches = list(SECTION_PATTERN.finditer(text))
        if len(matches) < 2:
            return self.fallback.chunk(text)

        chunks: list[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section = text[start:end].strip()
            if section:
                chunks.extend(self.fallback.chunk(section) if len(section) > 3000 else [section])
        return chunks

