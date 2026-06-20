"""LiteLLM provider for unified chat completion across 100+ models."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_litellm import ChatLiteLLM

from src.llm.providers.base import stream_llm_response


logger = logging.getLogger(__name__)


class LiteLLMProvider:
    """Universal chat completion provider using LiteLLM."""

    def __init__(self, model: str, temperature: float, max_tokens: int, **kwargs: Any) -> None:
        """Initialize the provider and build the underlying LiteLLM client.

        Args:
          model: LiteLLM-formatted model identifier (e.g. "gemini/gemini-1.5-pro").
          temperature: Sampling temperature.
          max_tokens: Maximum tokens to generate.
          **kwargs: Reserved for future provider options; currently unused.
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        # ChatLiteLLM will automatically pick up API keys from os.environ
        self.llm = self._build_llm()

    def _build_llm(self) -> ChatLiteLLM:
        return ChatLiteLLM(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    @staticmethod
    def _convert_messages(messages: list[dict[str, str]]) -> list[SystemMessage | HumanMessage]:
        """Convert role/content dicts to LangChain message objects.

        Args:
          messages: Chat messages with "role" ("system" or "user") and
            "content" keys. Other roles are silently dropped.

        Returns:
          The corresponding list of SystemMessage/HumanMessage objects.
        """
        converted: list[SystemMessage | HumanMessage] = []
        for msg in messages:
            if msg["role"] == "system":
                converted.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                converted.append(HumanMessage(content=msg["content"]))
        return converted

    async def get_chat_response(
        self,
        messages: list[dict[str, str]],
        stream: bool,
        websocket: Any = None,
    ) -> str:
        """Get a chat completion, optionally streaming partial output.

        Args:
          messages: Chat messages with "role" and "content" keys.
          stream: If True, streams partial output to `websocket` (or logs
            it) as it arrives.
          websocket: Optional WebSocket to stream partial output to.

        Returns:
          The completion text returned by the model.
        """
        converted = self._convert_messages(messages)
        if not stream:
            output = await self.llm.ainvoke(converted)
            return output.content

        return await stream_llm_response(self.llm, converted, websocket)
