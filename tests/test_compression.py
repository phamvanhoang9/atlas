import pytest
from unittest.mock import MagicMock, patch
from src.context.compression import ContextCompressor

@pytest.fixture
def mock_embeddings():
    embeddings = MagicMock()
    return embeddings

@pytest.fixture
def sample_docs():
    return [
        {"url": "url1", "raw_content": "This is a document about machine learning. Machine learning is a subset of AI."},
        {"url": "url2", "raw_content": "Quantum computing is a field of computing based on quantum mechanics."}
    ]

def test_compression_initialization(sample_docs, mock_embeddings):
    compressor = ContextCompressor(documents=sample_docs, embeddings=mock_embeddings)
    assert compressor.documents == sample_docs
    assert compressor.similarity_threshold == 0.55

@patch("src.context.compression.ContextCompressor._get_contextual_retriever")
def test_get_context_success(mock_get_retriever, sample_docs, mock_embeddings):
    # Mock documents returned by retriever
    mock_doc = MagicMock()
    mock_doc.page_content = "Relevant chunk"
    mock_doc.metadata = {"source": "url1", "title": "Title1"}
    
    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = [mock_doc]
    mock_get_retriever.return_value = mock_retriever
    
    compressor = ContextCompressor(documents=sample_docs, embeddings=mock_embeddings)
    context = compressor.get_context("machine learning")
    
    assert "Relevant chunk" in context
    assert "Source: url1" in context

@patch("src.context.compression.ContextCompressor._get_contextual_retriever")
def test_get_context_limits_documents_without_duplicates(mock_get_retriever, mock_embeddings):
    long_content = "x" * 5000
    documents = [
        {"url": "url1", "raw_content": long_content},
        {"url": "url2", "raw_content": "short content"},
    ]
    captured_documents = []

    def make_retriever(limited_docs):
        captured_documents.extend(limited_docs)
        mock_doc = MagicMock()
        mock_doc.page_content = "Relevant chunk"
        mock_doc.metadata = {"source": "url1", "title": "Title1"}
        mock_retriever = MagicMock()
        mock_retriever.invoke.return_value = [mock_doc]
        return mock_retriever

    mock_get_retriever.side_effect = make_retriever

    compressor = ContextCompressor(documents=documents, embeddings=mock_embeddings)
    context = compressor.get_context("machine learning")

    assert "Relevant chunk" in context
    assert len(captured_documents) == 2
    assert captured_documents[0]["raw_content"] == long_content
    assert captured_documents[1]["raw_content"] == "short content"

@patch("src.context.compression.ContextCompressor._get_contextual_retriever")
def test_get_context_fallback(mock_get_retriever, sample_docs, mock_embeddings):
    # Mock no documents found
    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = []
    mock_get_retriever.return_value = mock_retriever
    
    compressor = ContextCompressor(documents=sample_docs, embeddings=mock_embeddings)
    context = compressor.get_context("something else")
    
    # Should use fallback
    assert "Source: url1" in context
    assert "This is a document about machine learning" in context

def test_pretty_print_docs(sample_docs, mock_embeddings):
    compressor = ContextCompressor(documents=sample_docs, embeddings=mock_embeddings)
    
    mock_doc = MagicMock()
    mock_doc.page_content = "Content"
    mock_doc.metadata = {"source": "url", "title": "Title"}
    
    output = compressor._pretty_print_docs([mock_doc], 1)
    assert "Source: url" in output
    assert "Title: Title" in output
    assert "Content: Content" in output
