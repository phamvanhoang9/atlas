"""Semantic compression of search results into LLM-ready context."""

import logging
import re
from typing import Any, Optional, Sequence

from langchain_classic.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_classic.retrievers.document_compressors import (
    DocumentCompressorPipeline,
    EmbeddingsFilter,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .retriever import SearchAPIRetriever
from src.config import Config
from src.rag.reranking import CrossEncoderReranker
from src.utils.config_utils import resolve


logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(
    r"(?m)^(?=(?:#+\s|\d+\.\s+[A-Z]|(?:Abstract|Introduction|Background|Related Work|"
    r"Methodology|Methods|Approach|Experiments?|Results?|Discussion|Conclusion|"
    r"References?|Appendix)\b))",
    re.IGNORECASE,
)
_HEADER_RE = re.compile(r"^(?:#+\s*|(?:\d+\.)+\s*)(.{0,80})")


class SectionAwareTextSplitter(RecursiveCharacterTextSplitter):
    """Splits academic text at section boundaries before character-based chunking.

    Each sub-chunk is prefixed with its section header so the retriever knows
    which part of the paper a chunk came from.
    """

    def split_text(self, text: str) -> list[str]:
        """Split text into chunks, prefixing each with its section header.

        Args:
          text: The document text to split.

        Returns:
          A list of chunk strings. Chunks derived from oversized sections are
          prefixed with `[<header>]` so the originating section stays
          identifiable; falls back to plain character-based splitting if no
          section boundaries are found.
        """
        sections = _SECTION_RE.split(text)
        if len(sections) <= 1:
            return super().split_text(text)

        chunks: list[str] = []
        for section in sections:
            section = section.strip()
            if not section:
                continue
            first_line, _, body = section.partition("\n")
            header_match = _HEADER_RE.match(first_line.strip())
            header = header_match.group(1).strip() if header_match else first_line.strip()[:60]
            if len(section) <= self._chunk_size:
                chunks.append(section)
            else:
                for sub in super().split_text(body or section):
                    chunks.append(f"[{header}] {sub}" if header and not sub.startswith("[") else sub)
        return chunks or super().split_text(text)


class ContextCompressor:
    """Compresses search results into relevant, citation-ready context.

    Splits documents into section-aware chunks, embeds and filters them by
    similarity to the query, and optionally reranks survivors with a
    `CrossEncoderReranker`. Falls back to raw, untrimmed document excerpts if
    compression errors out or yields no usable chunks, so callers always get
    some context back.
    """

    def __init__(
        self,
        documents: Optional[list[dict[str, Any]]],
        embeddings: Any,
        max_results: int = 5,
        *,
        similaritiy_threshold: Optional[float] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        cfg: Optional["Config"] = None,
    ) -> None:
        """Initialize the compressor with documents and chunking/filter settings.

        Args:
          documents: Search result documents to compress; each expected to
            provide `raw_content` and `url` at minimum. Treated as empty if
            None.
          embeddings: A LangChain-compatible embeddings object used for the
            similarity filter.
          max_results: Maximum number of chunks/snippets to return.
          similaritiy_threshold: Minimum embedding similarity score for a
            chunk to survive filtering. Falls back to `cfg.similarity_threshold`
            or 0.55 when omitted.
          chunk_size: Character size passed to the section-aware splitter.
            Falls back to `cfg.chunk_size` or 1000 when omitted.
          chunk_overlap: Character overlap between adjacent chunks. Falls
            back to `cfg.chunk_overlap` or 200 when omitted.
          cfg: Config instance used to resolve unset parameters; defaults to
            a fresh `Config()`.
        """
        self.documents = documents or []
        self.embeddings = embeddings
        self.max_results = max_results

        self.cfg = cfg or Config()

        self.similarity_threshold = resolve(similaritiy_threshold, self.cfg, "similarity_threshold", 0.55)
        self.chunk_size = resolve(chunk_size, self.cfg, "chunk_size", 1000)
        self.chunk_overlap = resolve(chunk_overlap, self.cfg, "chunk_overlap", 200)
        self.reranker = CrossEncoderReranker.from_env()

    def _limit_documents(self, documents: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        # Bug B8 Fix: Do not truncate documents. Let RecursiveCharacterTextSplitter do its job.
        return list(documents)

    def _get_contextual_retriever(
        self,
        documents: Optional[Sequence[dict[str, Any]]] = None,
        *,
        similarity_threshold: Optional[float] = None,
    ) -> ContextualCompressionRetriever:
        """Build a retriever that splits, embeds, and filters documents by similarity.

        Args:
          documents: Documents to retrieve over; defaults to `self.documents`
            when omitted.
          similarity_threshold: Overrides `self.similarity_threshold` for
            this retriever instance (used to retry with a relaxed threshold).

        Returns:
          A `ContextualCompressionRetriever` chaining section-aware splitting
          and an embeddings-based relevance filter.
        """
        threshold = similarity_threshold if similarity_threshold is not None else self.similarity_threshold
        splitter = SectionAwareTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        relevance_filter = EmbeddingsFilter(embeddings=self.embeddings, similarity_threshold=threshold)
        pipeline_compressor = DocumentCompressorPipeline(
            transformers=[splitter, relevance_filter]
        )
        base_retriever = SearchAPIRetriever(
            pages=list(self.documents if documents is None else documents)
        )
        contextual_retriever = ContextualCompressionRetriever(
            base_compressor=pipeline_compressor, base_retriever=base_retriever
        )
        return contextual_retriever

    def _pretty_print_docs(self, docs: Sequence[Any], top_n: int) -> str:
        """Format the first `top_n` docs as source/title/content text blocks."""
        return "\n".join(
            f"Source: {doc.metadata.get('source')}\n"
            f"Title: {doc.metadata.get('title')}\n"
            f"Content: {doc.page_content}\n"
            for index, doc in enumerate(docs)
            if index < top_n
        )

    def _build_fallback_context(
        self,
        documents: Sequence[dict[str, Any]],
        max_results: int,
    ) -> str:
        """Build raw, untrimmed context (each doc capped at 1000 chars) as a fallback."""
        return "\n\n".join(
            f"Source: {doc.get('url')}\nContent: {doc.get('raw_content', '')[:1000]}..."
            for doc in documents[:max_results]
        )

    _MIN_CHUNKS = 2  # minimum chunks needed for downstream metrics (RAGAS etc.)

    def get_context(self, query: str, max_results: int = 5) -> str:
        """Get compressed, query-relevant context with error handling and fallback.

        Splits and embeds documents, filters by similarity to `query`, and
        relaxes the similarity threshold once if too few chunks survive (see
        `_MIN_CHUNKS`). Reranks survivors with `self.reranker` when enabled.
        Falls back to raw document excerpts if compression raises, finds no
        chunks, or produces empty formatted output.

        Args:
          query: The research query to filter and rerank chunks against.
          max_results: Maximum number of chunks to include in the output.

        Returns:
          Formatted context text combining the most relevant chunks (or raw
          fallback excerpts if compression fails).
        """
        try:
            limited_docs = self._limit_documents(self.documents)
            compressed_docs = self._get_contextual_retriever(limited_docs)
            relevant_docs = compressed_docs.invoke(query)

            # If fewer than _MIN_CHUNKS survived the threshold, relax it once so
            # downstream consumers (RAGAS, evaluation metrics) always have enough
            # context. Relaxed threshold = current − 0.15, clamped to 0.20.
            if len(relevant_docs) < self._MIN_CHUNKS and self.similarity_threshold > 0.25:
                relaxed = max(0.20, self.similarity_threshold - 0.15)
                logger.info(
                    "Only %d chunk(s) above threshold %.2f; relaxing to %.2f for min-coverage docs=%d",
                    len(relevant_docs), self.similarity_threshold, relaxed, len(limited_docs),
                )
                relaxed_retriever = self._get_contextual_retriever(limited_docs, similarity_threshold=relaxed)
                relaxed_docs = relaxed_retriever.invoke(query)
                if len(relaxed_docs) > len(relevant_docs):
                    relevant_docs = relaxed_docs

            if not relevant_docs:
                logger.info(
                    "Context compression found no chunks above threshold; using raw fallback docs=%s query_len=%s threshold=%.2f chunk_size=%s chunk_overlap=%s",
                    len(limited_docs),
                    len(query),
                    self.similarity_threshold,
                    self.chunk_size,
                    self.chunk_overlap,
                )
                return self._build_fallback_context(limited_docs, max_results)

            relevant_docs = self.reranker.rerank_documents(query, relevant_docs)
            result = self._pretty_print_docs(relevant_docs, max_results)
            if not result:
                logger.warning(
                    "Context compression produced empty formatted output; using raw fallback docs=%s relevant_docs=%s",
                    len(limited_docs),
                    len(relevant_docs),
                )
                return self._build_fallback_context(limited_docs, max_results)
            return result
        except (RuntimeError, TypeError, ValueError) as exc:
            logger.exception("Error in context compression, using fallback: %s", exc)
            return self._build_fallback_context(self.documents, max_results)
