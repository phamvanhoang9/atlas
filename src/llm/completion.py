"""Unified chat completion with retry handling and LiteLLM integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from fastapi import WebSocket
from litellm.exceptions import APIConnectionError, Timeout, InternalServerError, RateLimitError

from src.llm.providers.litellm_provider import LiteLLMProvider
from src.llm.router import route_model

logger = logging.getLogger(__name__)


RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = tuple(
    exc
    for exc in (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.TimeoutException,
        APIConnectionError,
        Timeout,
        InternalServerError,
        RateLimitError,
    )
    if exc is not None
)

RETRY_DELAYS_SECONDS = (2.0, 4.0, 8.0)


async def create_chat_completion(
    messages: list[dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.9,
    max_tokens: Optional[int] = None,
    llm_provider: Optional[str] = None,
    stream: Optional[bool] = False,
    websocket: WebSocket | None = None,
    llm_kwargs: dict[str, Any] | None = None,
    report_type: Optional[str] = None,
) -> str:
    """Create a chat completion with exponential-backoff retry and model routing."""
    if model is None:
        raise ValueError("Model cannot be None")
    if llm_provider is None:
        raise ValueError("LLM provider cannot be None")
    if max_tokens is not None and max_tokens > 12001:
        raise ValueError(f"Max tokens cannot be more than 12001, but got {max_tokens}")

    # Route model based on task complexity
    routed_model = route_model(
        report_type=report_type or "hỏi đáp",
        requested_model=model,
        provider=llm_provider,
    )

    # Format model string for LiteLLM (e.g. "gemini/gemini-1.5-pro")
    litellm_model = routed_model
    if llm_provider == "google" and not litellm_model.startswith("gemini/"):
        litellm_model = f"gemini/{litellm_model}"

    logger.info(
        "LLM completion start provider=%s requested_model=%s routed_model=%s report_type=%s stream=%s messages=%s max_tokens=%s",
        llm_provider,
        model,
        litellm_model,
        report_type,
        bool(stream),
        len(messages),
        max_tokens,
    )

    provider = LiteLLMProvider(
        model=litellm_model,
        temperature=temperature,
        max_tokens=max_tokens,
        **(llm_kwargs or {}),
    )

    max_attempts = len(RETRY_DELAYS_SECONDS) + 1
    for attempt in range(max_attempts):
        try:
            response = await provider.get_chat_response(
                messages=messages,
                stream=bool(stream),
                websocket=websocket,
            )
            logger.info(
                "LLM completion complete provider=%s model=%s attempt=%s response_chars=%s",
                llm_provider,
                litellm_model,
                attempt + 1,
                len(response),
            )
            return response
        except RETRYABLE_EXCEPTIONS as exc:
            if attempt == max_attempts - 1:
                logger.error(
                    "LLM provider %s failed after %s attempts: %s",
                    llm_provider,
                    max_attempts,
                    exc,
                )
                raise RuntimeError(
                    f"Failed to get response from {llm_provider} API after {max_attempts} attempts"
                ) from exc

            wait_time = RETRY_DELAYS_SECONDS[attempt]
            logger.warning(
                "Retryable LLM provider error on attempt %s/%s for %s: %s. Retrying in %.1fs",
                attempt + 1,
                max_attempts,
                llm_provider,
                exc,
                wait_time,
            )
            await asyncio.sleep(wait_time)

    raise RuntimeError(f"Failed to get response from {llm_provider} API after {max_attempts} attempts")
