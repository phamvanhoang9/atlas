"""Stream output to WebSocket clients and console."""

import asyncio
import logging
from typing import Any


logger = logging.getLogger(__name__)


async def stream_output(
    type: str,
    output: Any,
    websocket: Any = None,
    log_to_console: bool = True,
) -> None:
    """Stream output to the websocket.

    Args:
        type: Message type (e.g. ``"logs"``, ``"report"``).
        output: Payload to send.
        websocket: Optional websocket or wrapper that exposes ``send_json``.
        log_to_console: Whether to also log to the console.
    """
    if not websocket or log_to_console:
        try:
            # If the string contains emojis, the Windows console might crash with UnicodeEncodeError
            # unless the console is configured for UTF-8. We use a safe log approach.
            if isinstance(output, str):
                logger.info(output.encode("utf-8", "replace").decode("utf-8"))
            else:
                logger.info(output)
        except (UnicodeEncodeError, RuntimeError, OSError, ValueError, TypeError) as exc:
            logger.debug("Failed to log streamed output safely: %s", exc)

    if websocket:
        try:
            await websocket.send_json({"type": type, "output": output})
            await asyncio.sleep(0.01)
        except (RuntimeError, OSError) as exc:
            logger.error("Error sending websocket message: %s", exc)
