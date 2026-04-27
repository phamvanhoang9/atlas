import pytest
from unittest.mock import MagicMock, patch
import os
from pathlib import Path
from uuid import uuid4
from src.retrievers.tavily_search.tavily_search import TavilySearch

@patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"})
def test_tavily_initialization():
    searcher = TavilySearch(query="test query")
    assert searcher.query == "test query"
    assert searcher.api_key == "test-key"

@patch.dict(os.environ, {}, clear=True)
def test_tavily_key_error():
    with pytest.raises(Exception) as excinfo:
        TavilySearch(query="test")
    assert "Tavily API key not found" in str(excinfo.value)

@patch("src.retrievers.tavily_search.tavily_search.TavilyClient")
@patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"})
def test_tavily_search_success(mock_client_class):
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {"url": "https://arxiv.org/123", "content": "paper content"}
        ]
    }
    mock_client_class.return_value = mock_client
    
    searcher = TavilySearch(query="test")
    results = searcher.search()
    
    assert len(results) == 1
    assert results[0]["href"] == "https://arxiv.org/123"
    assert results[0]["body"] == "paper content"
    mock_client.search.assert_called_once()

@patch("src.retrievers.tavily_search.tavily_search.TavilyClient")
@patch("src.retrievers.tavily_search.tavily_search.DDGS")
@patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"})
def test_tavily_search_fallback(mock_ddg_class, mock_client_class):
    # Tavily fails
    mock_client = MagicMock()
    mock_client.search.side_effect = RuntimeError("API Error")
    mock_client_class.return_value = mock_client
    
    # DDG works
    mock_ddg = MagicMock()
    mock_ddg.text.return_value = [{"href": "ddg-url", "body": "ddg-content"}]
    mock_ddg_class.return_value = mock_ddg
    
    searcher = TavilySearch(query="test")
    results = searcher.search()
    
    assert len(results) == 1
    assert results[0]["href"] == "ddg-url"
    assert results[0]["body"] == "ddg-content"

@patch("src.retrievers.tavily_search.tavily_search.TavilyClient")
@patch.dict(os.environ, {"TAVILY_API_KEY": "test-key", "ENABLE_SEARCH_CACHE": "true"})
def test_tavily_search_uses_cache(mock_client_class, monkeypatch):
    cache_path = Path(".atlas_cache") / f"test_search_cache_{uuid4().hex}.sqlite"
    monkeypatch.setenv("ATLAS_CACHE_DB", str(cache_path))

    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {"url": "https://arxiv.org/123", "content": "paper content"}
        ]
    }
    mock_client_class.return_value = mock_client

    first = TavilySearch(query="cached query").search()
    second = TavilySearch(query="cached query").search()

    assert first == second
    assert mock_client.search.call_count == 1
