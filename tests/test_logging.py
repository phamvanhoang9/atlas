"""Tests for the terminal logging module (src/observability/logging.py)."""

from __future__ import annotations

import logging

from src.observability.logging import ColorFormatter, setup_logging


def _record(level: int = logging.INFO, name: str = "src.demo", msg: str = "hello") -> logging.LogRecord:
    """Build a minimal `LogRecord` for exercising `ColorFormatter.format()`."""
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None
    )


def test_color_formatter_adds_ansi_when_enabled() -> None:
    out = ColorFormatter(use_color=True).format(_record(logging.ERROR, msg="boom"))
    assert "\x1b[" in out and "boom" in out


def test_color_formatter_plain_when_disabled() -> None:
    out = ColorFormatter(use_color=False).format(_record(logging.INFO, msg="plain"))
    assert "\x1b[" not in out
    assert "plain" in out
    assert "INFO" in out


def test_color_formatter_shortens_module_name() -> None:
    out = ColorFormatter(use_color=False).format(_record(name="src.orchestration.runner"))
    # The long dotted path is collapsed to its final segment.
    assert "runner" in out
    assert "src.orchestration.runner" not in out


def test_setup_logging_is_idempotent_and_quiets_noisy_loggers() -> None:
    setup_logging(level=logging.INFO)
    count = len(logging.getLogger().handlers)
    setup_logging(level=logging.INFO)
    assert len(logging.getLogger().handlers) == count  # no handler pile-up
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("litellm").level >= logging.WARNING
