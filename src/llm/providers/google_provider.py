"""Google Gemini LLM provider."""

import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.llm.providers.base import stream_llm_response


logger = logging.getLogger(__name__)


class GoogleProvider:
    """Google Gemini chat completion provider."""

    def __init__(self, model: str, temperature: float, max_tokens: int, **kwargs: Any) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = self._get_api_key()
        self.llm = self._build_llm()

    @staticmethod
    def _get_api_key() -> str:
        try:
            return os.environ["GEMINI_API_KEY"]
        except KeyError as exc:
            raise RuntimeError(
                "GEMINI API key not found. Set the GEMINI_API_KEY environment variable."
            ) from exc

    def _build_llm(self) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=self.model,
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            google_api_key=self.api_key,
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
        if not stream:
            converted = self._convert_messages(messages)
            output = await self.llm.ainvoke(converted)
            return output.content

        return await stream_llm_response(self.llm, messages, websocket)
