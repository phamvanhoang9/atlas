"""OpenAI LLM provider."""

import logging
import os
from typing import Any

import httpx
from langchain_openai import ChatOpenAI

from src.llm.providers.base import stream_llm_response


logger = logging.getLogger(__name__)


class OpenAIProvider:
    """OpenAI / OpenAI-compatible chat completion provider."""

    def __init__(self, model: str, temperature: float, max_tokens: int, **kwargs: Any) -> None:
        """Initialize the provider and build the underlying ChatOpenAI client.

        Args:
          model: OpenAI model identifier (e.g. "gpt-4o").
          temperature: Sampling temperature.
          max_tokens: Maximum tokens to generate.
          **kwargs: Reserved for future provider options; currently unused.

        Raises:
          RuntimeError: If the OPENAI_API_KEY environment variable is unset.
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = self._get_api_key()
        self.base_url = os.environ.get("OPENAI_BASE_URL", None)
        self.llm = self._build_llm()

    @staticmethod
    def _get_api_key() -> str:
        """Return the OpenAI API key from the environment.

        Raises:
          RuntimeError: If OPENAI_API_KEY is not set.
        """
        try:
            return os.environ["OPENAI_API_KEY"]
        except KeyError as exc:
            raise RuntimeError(
                "OpenAI API key not found. Set the OPENAI_API_KEY environment variable."
            ) from exc

    def _build_llm(self) -> ChatOpenAI:
        llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=self.api_key,
        )
        if self.base_url:
            llm.openai_api_base = self.base_url
        return llm

    async def get_chat_response(
        self,
        messages: list[dict[str, Any]],
        stream: bool,
        websocket: Any = None,
    ) -> str:
        """Get a chat completion, optionally streaming partial output.

        Args:
          messages: Chat messages in OpenAI-style role/content dict form.
          stream: If True, streams partial output to `websocket` (or logs
            it) as it arrives.
          websocket: Optional WebSocket to stream partial output to.

        Returns:
          The completion text returned by the model.

        Raises:
          httpx.ReadError: If a network error occurs while streaming.
        """
        if not stream:
            output = await self.llm.ainvoke(messages)
            return output.content

        try:
            return await stream_llm_response(self.llm, messages, websocket)
        except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as exc:
            raise httpx.ReadError(f"Network error during streaming: {exc}") from exc
