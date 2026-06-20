"""Base LLM provider protocol — all providers must implement this."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable


logger = logging.getLogger(__name__)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol that all LLM providers must satisfy."""

    async def get_chat_response(
        self,
        messages: list[dict[str, Any]],
        stream: bool,
        websocket: Any = None,
    ) -> str:
        """Return the completion text for the given messages.

        Args:
          messages: Chat messages in OpenAI-style role/content dict form.
          stream: If True, streams partial output to `websocket` (or logs
            it) as it arrives.
          websocket: Optional WebSocket to stream partial output to.

        Returns:
          The completion text returned by the provider.
        """
        ...


async def stream_llm_response(
    llm: Any,
    messages: list[dict[str, Any]],
    websocket: Any = None,
) -> str:
    """Stream a chat completion from a LangChain chat model.

    Buffers content and flushes on newline boundaries to provide
    smooth streaming to the client while avoiding per-token overhead.

    Args:
      llm: A LangChain chat model exposing an `astream()` async generator.
      messages: Chat messages in LangChain or role/content dict form,
        as accepted by `llm.astream()`.
      websocket: Optional WebSocket to send `{"type": "report", "output":
        ...}` chunks to as they are flushed. If None, chunks are logged
        instead.

    Returns:
      The full concatenated completion text.
    """
    paragraph = ""
    response = ""

    async for chunk in llm.astream(messages):
        content = chunk.content
        if content is not None:
            response += content
            paragraph += content
            if "\n" in paragraph:
                if websocket is not None:
                    try:
                        await websocket.send_json({"type": "report", "output": paragraph})
                        await asyncio.sleep(0.01)
                    except (RuntimeError, OSError) as exc:
                        logger.warning("Error sending stream: %s", exc)
                else:
                    logger.info("%s", paragraph)
                paragraph = ""

    # Flush remaining content
    if paragraph:
        if websocket is not None:
            try:
                await websocket.send_json({"type": "report", "output": paragraph})
            except (RuntimeError, OSError) as exc:
                logger.warning("Error sending final paragraph: %s", exc)
        else:
            logger.info("%s", paragraph)

    return response
