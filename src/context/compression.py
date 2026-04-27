import logging
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


class ContextCompressor:
    """
    Compresses and filters documents using embeddings and semantic similarity.
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
    ) -> ContextualCompressionRetriever:
        splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        relevance_filter = EmbeddingsFilter(embeddings=self.embeddings, similarity_threshold=self.similarity_threshold)
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
        return "\n\n".join(
            f"Source: {doc.get('url')}\nContent: {doc.get('raw_content', '')[:1000]}..."
            for doc in documents[:max_results]
        )

    def get_context(self, query: str, max_results: int = 5) -> str:
        """
        Get compressed context with error handling and fallback.
        """
        try:
            limited_docs = self._limit_documents(self.documents)
            compressed_docs = self._get_contextual_retriever(limited_docs)
            relevant_docs = compressed_docs.invoke(query)

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
