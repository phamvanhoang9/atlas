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
    ) -> str: ...


async def stream_llm_response(
    llm: Any,
    messages: list[dict[str, Any]],
    websocket: Any = None,
) -> str:
    """Shared streaming logic for LLM providers.

    Buffers content and flushes on newline boundaries to provide
    smooth streaming to the client while avoiding per-token overhead.
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
