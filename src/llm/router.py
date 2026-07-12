"""LLM model router based on task complexity.

Three explicit tiers (modes_redesign_plan.md Mục 7 Giai đoạn 1, trị finding
#1 "quick không nhanh ở tầng model"):

- ``ask``: force the cheap/fast model, even if the configured default is
  the stronger one — Ask must be genuinely cheap, not just "not deep".
- ``compare``: pass through whatever model is configured (the middle tier
  is "whatever the user's balanced default is"), no forced remap.
- ``deep_dive``: force the strongest currently-configured model.

Only two real per-provider tiers exist today (openai: gpt-4o-mini/gpt-4o;
google: gemini-1.5-flash/gemini-1.5-pro) since no new provider keys were
approved for Giai đoạn 0–1.5 (see modes_redesign_plan.md Mục 8.1 #9). A
genuinely separate reasoning-tier model (o-series/opus, lead+sub agents) is
deferred to Giai đoạn 4. Recognition is deliberately conservative: unrecognized
or custom/fine-tuned model strings are never remapped, so a user's explicit
model choice is never silently overridden.
"""

import logging
from typing import Optional

from src.modes import ASK, DEEP_DIVE, normalize_mode

logger = logging.getLogger(__name__)

_OPENAI_CHEAP = "gpt-4o-mini"
_OPENAI_STRONG = "gpt-4o"
_GOOGLE_CHEAP = "gemini-1.5-flash"
_GOOGLE_STRONG = "gemini-1.5-pro"


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

    tier = normalize_mode(report_type)

    if tier == ASK:
        if provider == "google" and requested_model == _GOOGLE_STRONG:
            logger.info("Routing from pro to flash for ask tier")
            return _GOOGLE_CHEAP
        if provider == "openai" and requested_model == _OPENAI_STRONG:
            logger.info("Routing from gpt-4o to gpt-4o-mini for ask tier")
            return _OPENAI_CHEAP
        return requested_model

    if tier == DEEP_DIVE:
        if provider == "google" and requested_model == _GOOGLE_CHEAP:
            logger.info("Routing from flash to pro for deep_dive tier")
            return _GOOGLE_STRONG
        if provider == "openai" and requested_model == _OPENAI_CHEAP:
            logger.info("Routing from gpt-4o-mini to gpt-4o for deep_dive tier")
            return _OPENAI_STRONG
        return requested_model

    # compare tier (and any unrecognized report_type, which normalize_mode
    # already falls back to "compare" for): pass through unchanged.
    return requested_model
