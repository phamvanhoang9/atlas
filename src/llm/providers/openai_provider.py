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
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = self._get_api_key()
        self.base_url = os.environ.get("OPENAI_BASE_URL", None)
        self.llm = self._build_llm()

    @staticmethod
    def _get_api_key() -> str:
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
        if not stream:
            output = await self.llm.ainvoke(messages)
            return output.content

        try:
            return await stream_llm_response(self.llm, messages, websocket)
        except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as exc:
            raise httpx.ReadError(f"Network error during streaming: {exc}") from exc
