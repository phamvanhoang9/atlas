"""Tests for the legacy LLM provider wrappers and chat completion retry logic.

Covers OpenAI/Google provider initialization and chat response handling
(`src/llm_provider/`), plus retry-on-transient-error behavior in
`create_chat_completion` (`src/utils/llm.py`).
"""

import pytest
import httpx
from unittest.mock import MagicMock, patch, AsyncMock
import os
from src.llm_provider.openai.openai import OpenAIProvider
from src.llm_provider.google.google import GoogleProvider
from src.utils.llm import create_chat_completion

@patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"})
@patch("src.llm_provider.openai.openai.ChatOpenAI")
def test_openai_provider_initialization(mock_chat_openai):
    provider = OpenAIProvider(model="gpt-4", temperature=0.5, max_tokens=100)
    assert provider.model == "gpt-4"
    assert provider.api_key == "test-openai-key"
    mock_chat_openai.assert_called_once()

@patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"})
@patch("src.llm_provider.openai.openai.ChatOpenAI")
@pytest.mark.asyncio
async def test_openai_get_chat_response_no_stream(mock_chat_openai_class):
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = "openai response"
    mock_llm.ainvoke.return_value = mock_response
    mock_chat_openai_class.return_value = mock_llm
    
    provider = OpenAIProvider(model="gpt-4", temperature=0.5, max_tokens=100)
    response = await provider.get_chat_response(messages=[{"role": "user", "content": "hi"}], stream=False)
    
    assert response == "openai response"
    mock_llm.ainvoke.assert_called_once()

@patch.dict(os.environ, {"GEMINI_API_KEY": "test-google-key"})
@patch("src.llm_provider.google.google.ChatGoogleGenerativeAI")
def test_google_provider_initialization(mock_chat_google):
    provider = GoogleProvider(model="gemini-pro", temperature=0.5, max_tokens=100)
    assert provider.model == "gemini-pro"
    assert provider.api_key == "test-google-key"
    mock_chat_google.assert_called_once()

@patch.dict(os.environ, {"GEMINI_API_KEY": "test-google-key"})
@patch("src.llm_provider.google.google.ChatGoogleGenerativeAI")
@pytest.mark.asyncio
async def test_google_get_chat_response_no_stream(mock_chat_google_class):
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = "google response"
    mock_llm.ainvoke.return_value = mock_response
    mock_chat_google_class.return_value = mock_llm
    
    provider = GoogleProvider(model="gemini-pro", temperature=0.5, max_tokens=100)
    response = await provider.get_chat_response(messages=[{"role": "user", "content": "hi"}], stream=False)
    
    assert response == "google response"
    mock_llm.ainvoke.assert_called_once()

@patch("src.utils.llm.asyncio.sleep", new_callable=AsyncMock)
@patch("src.utils.llm.get_llm")
@pytest.mark.asyncio
async def test_create_chat_completion_retries_retryable_errors(mock_get_llm, mock_sleep):
    provider = MagicMock()
    provider.get_chat_response = AsyncMock(side_effect=[httpx.ReadError("temporary"), "ok"])
    mock_get_llm.return_value = provider

    response = await create_chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4",
        temperature=0.1,
        max_tokens=100,
        llm_provider="openai",
    )

    assert response == "ok"
    assert provider.get_chat_response.await_count == 2
    mock_sleep.assert_awaited_once_with(2.0)
