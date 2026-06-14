"""Canonical research mode registry."""

from src.modes.registry import (
    CANONICAL_MODE_IDS,
    DEEP,
    LEGACY_MODE_ALIASES,
    MODES,
    QUICK,
    RESEARCH,
    ModeSpec,
    get_mode_spec,
    is_known_mode,
    normalize_mode,
)

__all__ = [
    "CANONICAL_MODE_IDS",
    "DEEP",
    "LEGACY_MODE_ALIASES",
    "MODES",
    "QUICK",
    "RESEARCH",
    "ModeSpec",
    "get_mode_spec",
    "is_known_mode",
    "normalize_mode",
]
