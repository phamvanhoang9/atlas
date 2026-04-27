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
        converted = self._convert_messages(messages)
        if not stream:
            output = await self.llm.ainvoke(converted)
            return output.content

        return await stream_llm_response(self.llm, converted, websocket)
