"""Tests for the embeddings memory layer: provider selection and caching.

Covers `Memory` provider initialization (OpenAI/HuggingFace/invalid) and
`CachedEmbeddings` reuse of previously computed document vectors via a
`SQLiteTTLCache`.
"""

import pytest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch, MagicMock
from src.memory.embeddings import CachedEmbeddings, Memory
from src.storage import SQLiteTTLCache

def test_memory_initialization_openai():
    with patch("src.memory.embeddings.OpenAIEmbeddings") as mock_openai:
        memory = Memory(embedding_provider="openai")
        assert memory.get_embeddings() is not None
        mock_openai.assert_called_once()

def test_memory_initialization_huggingface():
    # Mocking HuggingFaceEmbeddings which is imported inside the match case
    with patch("langchain_community.embeddings.HuggingFaceEmbeddings") as mock_hf:
        memory = Memory(embedding_provider="huggingface")
        assert memory.get_embeddings() is not None
        mock_hf.assert_called_once()

def test_memory_initialization_error():
    with pytest.raises(ValueError) as excinfo:
        Memory(embedding_provider="unknown")
    assert "Embedding provider not found" in str(excinfo.value)

def test_cached_embeddings_reuses_document_vectors():
    base_embeddings = MagicMock()
    base_embeddings.embed_documents.return_value = [[0.1, 0.2]]
    cache_path = Path(".atlas_cache") / f"test_embedding_cache_{uuid4().hex}.sqlite"
    cache = SQLiteTTLCache(cache_path)
    cached_embeddings = CachedEmbeddings(
        base_embeddings,
        namespace="test",
        ttl_seconds=60,
        cache=cache,
    )

    first = cached_embeddings.embed_documents(["same text"])
    second = cached_embeddings.embed_documents(["same text"])

    assert first == [[0.1, 0.2]]
    assert second == [[0.1, 0.2]]
    base_embeddings.embed_documents.assert_called_once_with(["same text"])
