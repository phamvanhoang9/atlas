from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from src.storage import SQLiteTTLCache


logger = logging.getLogger(__name__)

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


class CachedEmbeddings(Embeddings):
    """Caches embedding vectors for a LangChain-compatible embeddings provider.

    Wraps any `Embeddings` implementation and persists computed vectors in a
    `SQLiteTTLCache`, keyed by provider namespace, text, and embedding kind
    (query vs. document). Cache misses are batched through the underlying
    provider; cache hits skip the provider call entirely.
    """

    def __init__(
        self,
        embeddings: Any,
        *,
        namespace: str,
        ttl_seconds: int,
        cache: SQLiteTTLCache,
    ) -> None:
        self.embeddings = embeddings
        self.namespace = namespace
        self.ttl_seconds = ttl_seconds
        self.cache = cache

    def _key(self, text: str, kind: str) -> str:
        return self.cache.make_key(
            {
                "provider": self.namespace,
                "kind": kind,
                "text": text,
                "version": 1,
            }
        )

    def embed_query(self, text: str) -> list[float]:
        """Return the cached embedding for `text`, computing it on a cache miss."""
        key = self._key(text, "query")
        cached = self.cache.get("embeddings", key)
        if cached is not None:
            logger.debug("Embedding cache hit for query text")
            return list(cached)

        embedding = self.embeddings.embed_query(text)
        self.cache.set("embeddings", key, embedding, self.ttl_seconds)
        return embedding

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for `texts`, computing only the cache misses.

        Args:
          texts: Document texts to embed, in order.

        Returns:
          Embeddings in the same order as `texts`, mixing cached and
          newly-computed vectors.
        """
        results: list[list[float] | None] = []
        missing_indexes: list[int] = []
        missing_texts: list[str] = []

        for index, text in enumerate(texts):
            cached = self.cache.get("embeddings", self._key(text, "document"))
            if cached is None:
                results.append(None)
                missing_indexes.append(index)
                missing_texts.append(text)
            else:
                results.append(list(cached))

        if missing_texts:
            embedded = self.embeddings.embed_documents(missing_texts)
            for index, embedding in zip(missing_indexes, embedded, strict=True):
                text = texts[index]
                self.cache.set("embeddings", self._key(text, "document"), embedding, self.ttl_seconds)
                results[index] = embedding

        return [embedding for embedding in results if embedding is not None]

    async def aembed_query(self, text: str) -> list[float]:
        """Async version of `embed_query`; falls back to the sync path if unsupported."""
        key = self._key(text, "query")
        cached = self.cache.get("embeddings", key)
        if cached is not None:
            return list(cached)

        if hasattr(self.embeddings, "aembed_query"):
            embedding = await self.embeddings.aembed_query(text)
        else:
            embedding = self.embed_query(text)
        self.cache.set("embeddings", key, embedding, self.ttl_seconds)
        return embedding

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Async version of `embed_documents`; falls back to the sync path if unsupported."""
        if hasattr(self.embeddings, "aembed_documents"):
            results: list[list[float] | None] = []
            missing_indexes: list[int] = []
            missing_texts: list[str] = []

            for index, text in enumerate(texts):
                cached = self.cache.get("embeddings", self._key(text, "document"))
                if cached is None:
                    results.append(None)
                    missing_indexes.append(index)
                    missing_texts.append(text)
                else:
                    results.append(list(cached))

            if missing_texts:
                embedded = await self.embeddings.aembed_documents(missing_texts)
                for index, embedding in zip(missing_indexes, embedded, strict=True):
                    text = texts[index]
                    self.cache.set("embeddings", self._key(text, "document"), embedding, self.ttl_seconds)
                    results[index] = embedding

            return [embedding for embedding in results if embedding is not None]

        return self.embed_documents(texts)


class Memory:
    """Constructs a (optionally cached) embeddings provider by name."""

    def __init__(self, embedding_provider: str, **kwargs: Any) -> None:
        """Build the embeddings provider, wrapping it in a cache unless disabled.

        Args:
          embedding_provider: Provider id; one of "openai" or "huggingface".
          **kwargs: Currently unused; accepted for forward-compatible
            provider-specific options.

        Raises:
          ValueError: If `embedding_provider` is not a recognized provider id.
        """
        match embedding_provider:
            case "openai":
                embeddings = OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)
                namespace = f"openai:{OPENAI_EMBEDDING_MODEL}"
            case "huggingface":
                from langchain_community.embeddings import HuggingFaceEmbeddings

                embeddings = HuggingFaceEmbeddings()
                namespace = "huggingface:default"
            case _:
                raise ValueError("Embedding provider not found.")

        cache_enabled = os.getenv("ENABLE_EMBEDDING_CACHE", "true").lower() == "true"
        if cache_enabled:
            ttl_seconds = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", "2592000"))
            embeddings = CachedEmbeddings(
                embeddings,
                namespace=namespace,
                ttl_seconds=ttl_seconds,
                cache=SQLiteTTLCache.from_env(),
            )

        self._embeddings = embeddings

    def get_embeddings(self) -> Any:
        """The configured embeddings provider (cached, if caching is enabled)."""
        return self._embeddings
