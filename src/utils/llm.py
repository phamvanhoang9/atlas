"""LLM provider lookup and chat completion with retry handling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from fastapi import WebSocket


logger = logging.getLogger(__name__)


try:
    from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
except ImportError:  # pragma: no cover - optional provider dependency
    APIConnectionError = APITimeoutError = InternalServerError = RateLimitError = None

try:
    from google.api_core.exceptions import DeadlineExceeded, ResourceExhausted, ServiceUnavailable
except ImportError:  # pragma: no cover - optional provider dependency
    DeadlineExceeded = ResourceExhausted = ServiceUnavailable = None


RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = tuple(
    exc
    for exc in (
        httpx.ReadError,
        httpx.ConnectError,
        httpx.TimeoutException,
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
        DeadlineExceeded,
        ResourceExhausted,
        ServiceUnavailable,
    )
    if exc is not None
)

RETRY_DELAYS_SECONDS = (2.0, 4.0, 8.0)


def get_llm(llm_provider: str, **kwargs: Any) -> Any:
    """Instantiate the provider class for *llm_provider*.

    Args:
      llm_provider: Provider id, e.g. ``"openai"`` or ``"google"``.
      **kwargs: Forwarded to the provider class constructor.

    Returns:
      An initialized provider instance.

    Raises:
      ValueError: If *llm_provider* is not a supported provider id.
    """
    match llm_provider:
        case "openai":
            from ..llm_provider import OpenAIProvider

            provider_class = OpenAIProvider
        case "google":
            from ..llm_provider import GoogleProvider

            provider_class = GoogleProvider
        case _:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")

    return provider_class(**kwargs)


async def create_chat_completion(
    messages: list[dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.9,
    max_tokens: Optional[int] = None,
    llm_provider: Optional[str] = None,
    stream: Optional[bool] = False,
    websocket: WebSocket | None = None,
    llm_kwargs: dict[str, Any] | None = None,
) -> str:
    """Create a chat completion with retry handling for transient provider failures.

    Retries on a fixed set of transient network/provider exceptions
    (``RETRYABLE_EXCEPTIONS``) using the backoff schedule in
    ``RETRY_DELAYS_SECONDS``, then gives up.

    Args:
      messages: Chat messages in OpenAI-style ``{"role", "content"}`` form.
      model: Model identifier; required.
      temperature: Sampling temperature.
      max_tokens: Optional cap on generated tokens; must be <= 12001.
      llm_provider: Provider id (e.g. ``"openai"``, ``"google"``); required.
      stream: Whether to stream tokens to *websocket* as they arrive.
      websocket: Optional websocket to stream tokens to.
      llm_kwargs: Extra keyword arguments forwarded to the provider constructor.

    Returns:
      The completed chat response text.

    Raises:
      ValueError: If *model* or *llm_provider* is ``None``, or *max_tokens*
        exceeds 12001.
      RuntimeError: If all retry attempts are exhausted.
    """
    if model is None:
        raise ValueError("Model cannot be None")
    if llm_provider is None:
        raise ValueError("LLM provider cannot be None")
    if max_tokens is not None and max_tokens > 12001:
        raise ValueError(f"Max tokens cannot be more than 12001, but got {max_tokens}")

    provider = get_llm(
        llm_provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **(llm_kwargs or {}),
    )

    max_attempts = len(RETRY_DELAYS_SECONDS) + 1
    for attempt in range(max_attempts):
        try:
            return await provider.get_chat_response(
                messages=messages,
                stream=bool(stream),
                websocket=websocket,
            )
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
