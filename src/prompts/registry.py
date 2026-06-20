"""Render named prompt templates with variable substitution."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Any

from .loader import PromptTemplate, load_prompt_template


logger = logging.getLogger(__name__)
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _normalize_value(value: Any) -> str:
    """Coerce *value* to a string, joining list/tuple items with blank lines."""
    if isinstance(value, list):
        return "\n\n".join(str(item) for item in value)
    if isinstance(value, tuple):
        return "\n\n".join(str(item) for item in value)
    return str(value)


@lru_cache(maxsize=32)
def _get_template(name: str) -> PromptTemplate:
    path = _TEMPLATE_DIR / f"{name}.yaml"
    return load_prompt_template(path)


def render_prompt(name: str, variables: dict[str, Any]) -> str | None:
    """Render the named template with *variables* substituted in.

    Templates are loaded from ``src/prompts/templates/{name}.yaml`` and
    cached. Lists/tuples in *variables* are flattened to strings (see
    ``_normalize_value``) before substitution.

    Args:
      name: Template name, without the ``.yaml`` extension.
      variables: Values to substitute into the template via
        ``string.Template.safe_substitute``.

    Returns:
      The rendered prompt text, or ``None`` if the template is missing
      or malformed (logged as a warning rather than raised).
    """
    try:
        prompt = _get_template(name)
        normalized = {key: _normalize_value(value) for key, value in variables.items()}
        return Template(prompt.template).safe_substitute(normalized)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Prompt template '%s' unavailable, falling back: %s", name, exc)
        return None
