"""LLM model router based on task complexity."""

import logging
from typing import Optional

from src.modes import DEEP_DIVE, normalize_mode

logger = logging.getLogger(__name__)


def route_model(
    report_type: str,
    requested_model: str,
    provider: str,
    override_model: Optional[str] = None
) -> str:
    """Determine the optimal model based on the task type.

    Args:
        report_type: The canonical mode id being generated for (see
            src.modes.registry).
        requested_model: The default model from configuration
        provider: The LLM provider (openai, google)
        override_model: An explicit override (if any)

    Returns:
        The model identifier to use.
    """
    if override_model:
        return override_model

    is_complex = normalize_mode(report_type) == DEEP_DIVE

    if provider == "google":
        if is_complex:
            if "flash" in requested_model:
                logger.info("Routing from flash to pro for deep research")
                return "gemini-1.5-pro"
        else:
            if "pro" in requested_model:
                logger.info("Routing from pro to flash for simpler modes")
                return "gemini-1.5-flash"

    if provider == "openai" and is_complex and requested_model == "gpt-4o-mini":
        logger.info("Routing from gpt-4o-mini to gpt-4o for deep research")
        return "gpt-4o"

    return requested_model
