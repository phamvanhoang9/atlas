from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Sequence


logger = logging.getLogger(__name__)

DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class CrossEncoderReranker:
    model_name: str = DEFAULT_CROSS_ENCODER_MODEL
    enabled: bool = False
    _model: Any = field(default=None, init=False, repr=False)
    _load_failed: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_env(cls) -> "CrossEncoderReranker":
        return cls(
            model_name=os.getenv("CROSS_ENCODER_MODEL", DEFAULT_CROSS_ENCODER_MODEL),
            enabled=_env_flag("ENABLE_CROSS_ENCODER_RERANKING", False),
        )

    def _load_model(self) -> Any | None:
        if not self.enabled:
            return None
        if self._model is not None:
            return self._model
        if self._load_failed:
            return None

        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            self._load_failed = True
            logger.warning("Cross-encoder reranking disabled; sentence-transformers missing: %s", exc)
            return None

        try:
            self._model = CrossEncoder(self.model_name)
            logger.info("Loaded cross-encoder reranker: %s", self.model_name)
            return self._model
        except (RuntimeError, OSError, ValueError) as exc:
            self._load_failed = True
            logger.warning("Cross-encoder reranking disabled; model load failed: %s", exc)
            return None

    @staticmethod
    def _document_text(document: Any) -> str:
        page_content = getattr(document, "page_content", None)
        if isinstance(page_content, str):
            return page_content
        if isinstance(document, dict):
            raw_content = document.get("raw_content") or document.get("content") or document.get("text")
            if isinstance(raw_content, str):
                return raw_content
        return str(document)

    def rerank_documents(
        self,
        query: str,
        documents: Sequence[Any],
        top_k: int | None = None,
    ) -> list[Any]:
        docs = list(documents)
        if len(docs) <= 1:
            return docs

        model = self._load_model()
        if model is None:
            return docs

        pairs = [(query, self._document_text(document)) for document in docs]
        try:
            scores = model.predict(pairs)
            scored_docs = list(zip(docs, scores))
            ranked = sorted(scored_docs, key=lambda item: float(item[1]), reverse=True)
            limit = top_k if top_k is not None else len(ranked)
            return [document for document, _score in ranked[:limit]]
        except (RuntimeError, OSError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Cross-encoder reranking failed, using embedding order: %s", exc)
            return docs
