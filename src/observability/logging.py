"""Production-grade terminal logging for ATLAS.

A small, dependency-free colour formatter plus a one-call ``setup_logging`` that
installs it, quiets noisy third-party loggers, and (on Python 3.12) patches the
``multiprocess`` resource-tracker so the interpreter does not spew
``AttributeError: '_thread.RLock' object has no attribute '_recursion_count'``
on shutdown.

Colour is auto-disabled when stderr is not a TTY or when ``NO_COLOR`` is set, so
piped/redirected logs stay clean and grep-friendly.
"""

from __future__ import annotations

import logging
import os
import sys
import time

# ----------------------------------------------------------------- colour table

RESET = "\x1b[0m"
DIM = "\x1b[2m"
_LEVEL_COLOR = {
    logging.DEBUG: "\x1b[38;5;245m",     # grey
    logging.INFO: "\x1b[38;5;39m",       # cyan/blue
    logging.WARNING: "\x1b[38;5;214m",   # amber
    logging.ERROR: "\x1b[38;5;203m",     # red
    logging.CRITICAL: "\x1b[1;38;5;231;48;5;160m",  # bold white on red
}
SEP = "│"

# Third-party loggers that flood INFO output; raised to WARNING.
_NOISY_LOGGERS = (
    "httpx", "httpcore", "litellm", "LiteLLM", "urllib3",
    "sentence_transformers", "asyncio", "openai", "watchfiles",
)


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(sys.stderr, "isatty", lambda: False)())


class ColorFormatter(logging.Formatter):
    """Aligned, optionally-coloured single-line records:

    ``HH:MM:SS │ LEVEL    │ module       │ message``
    """

    def __init__(self, use_color: bool | None = None) -> None:
        super().__init__()
        self.use_color = _color_enabled() if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = record.levelname
        module = record.name.rsplit(".", 1)[-1][:12]
        message = record.getMessage()

        if self.use_color:
            color = _LEVEL_COLOR.get(record.levelno, "")
            ts_s = f"{DIM}{ts}{RESET}"
            level_s = f"{color}{level:<8}{RESET}"
            module_s = f"{DIM}{module:<12}{RESET}"
            sep = f"{DIM}{SEP}{RESET}"
            line = f"{ts_s} {sep} {level_s} {sep} {module_s} {sep} {message}"
        else:
            line = f"{ts} {SEP} {level:<8} {SEP} {module:<12} {SEP} {message}"

        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"
        return line


_CONFIGURED = False


def setup_logging(level: int = logging.INFO, *, use_color: bool | None = None) -> None:
    """Install the colour formatter on the root logger. Idempotent.

    Replaces any existing root handlers with a single stderr handler, sets the
    ``src`` tree to *level*, and raises noisy third-party loggers to WARNING.
    """
    global _CONFIGURED

    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ColorFormatter(use_color=use_color))

    # Replace handlers so repeated calls (tests, reloads) never pile up.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    logging.getLogger("src").setLevel(level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _CONFIGURED = True


def patch_multiprocess_resource_tracker() -> None:
    """multiprocess 0.70.x calls ``self._lock._recursion_count()`` in
    ``_stop_locked``, but ``_thread.RLock`` dropped that method in Python 3.12,
    raising ``AttributeError`` on process/interpreter exit. Replace
    ``_stop_locked`` with an identical copy that guards the call. External refs
    are bound as default args so the function stays valid during interpreter
    shutdown when module globals are set to ``None``.
    """
    if sys.version_info < (3, 12):
        return
    try:
        import os as _os
        import multiprocess.resource_tracker as _rt  # type: ignore[import-not-found]

        def _stop_locked(
            self: object,
            close: object = _os.close,
            waitpid: object = _os.waitpid,
            waitstatus_to_exitcode: object = _os.waitstatus_to_exitcode,
        ) -> None:
            try:
                rc = self._lock._recursion_count()  # type: ignore[attr-defined]
            except AttributeError:
                rc = 0
            if rc > 1:
                return self._reentrant_call_error()  # type: ignore[attr-defined]
            if self._fd is None:  # type: ignore[attr-defined]
                return
            if self._pid is None:  # type: ignore[attr-defined]
                return
            close(self._fd)  # type: ignore[operator,attr-defined]
            self._fd = None  # type: ignore[attr-defined]
            waitpid(self._pid, 0)  # type: ignore[operator,attr-defined]
            self._pid = None  # type: ignore[attr-defined]

        _rt.ResourceTracker._stop_locked = _stop_locked  # type: ignore[method-assign]
    except Exception:  # noqa: BLE001
        pass
