import os
import asyncio
import httpx
import logging
from typing import Any

from langchain_openai import ChatOpenAI


logger = logging.getLogger(__name__)


class OpenAIProvider:
    
    def __init__(self, model: str, temperature: float, max_tokens: int) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = self.get_api_key()
        self.base_url = self.get_base_url()
        self.llm = self.get_llm_model()

    def get_api_key(self) -> str:
        """
        Gets the OpenAI API key
        Returns:

        """
        try:
            api_key = os.environ["OPENAI_API_KEY"]
        except KeyError as exc:
            raise RuntimeError(
                "OpenAI API key not found. Please set the OPENAI_API_KEY environment variable."
            ) from exc
        return api_key

    def get_base_url(self) -> str | None:
        """
        Gets the OpenAI Base URL from the environment variable if defined otherwise use the default None
        Returns:

        """
        base_url = os.environ.get("OPENAI_BASE_URL", None)
        return base_url


    def get_llm_model(self) -> ChatOpenAI:
        # Initializing the chat model
        llm = ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            api_key=self.api_key
        )
        if self.base_url:
            llm.openai_api_base = self.base_url

        return llm

    async def get_chat_response(self, messages: list[dict[str, Any]], stream: bool, websocket: Any = None) -> str:
        if not stream:
            # Getting output from the model chain using ainvoke for asynchronous invoking
            output = await self.llm.ainvoke(messages)

            return output.content

        else:
            return await self.stream_response(messages, websocket)

    async def stream_response(self, messages: list[dict[str, Any]], websocket: Any = None) -> str:
        paragraph = ""
        response = ""

        # Streaming the response using the chain astream method from langchain
        try:
            async for chunk in self.llm.astream(messages):
                content = chunk.content
                if content is not None:
                    response += content
                    paragraph += content
                    if "\n" in paragraph:
                        if websocket is not None:
                            try:
                                await websocket.send_json({"type": "report", "output": paragraph})
                                await asyncio.sleep(0.01)  # Small delay for proper streaming
                            except (RuntimeError, OSError) as exc:
                                logger.warning("Error sending stream: %s", exc)
                        else:
                            logger.info("%s", paragraph)
                        paragraph = ""
        except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException) as e:
            # Re-raise network errors to be handled by retry logic
            raise httpx.ReadError(f"Network error during streaming: {str(e)}")
        
        # Send any remaining paragraph content (fixes cut-off words issue)
        if paragraph:
            if websocket is not None:
                try:
                    await websocket.send_json({"type": "report", "output": paragraph})
                except (RuntimeError, OSError) as exc:
                    logger.warning("Error sending final paragraph: %s", exc)
            else:
                logger.info("%s", paragraph)

        return response
