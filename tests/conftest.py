import os
import sys


def _patch_multiprocess_resource_tracker() -> None:
    """multiprocess 0.70.x calls self._lock._recursion_count() in _stop_locked,
    but _thread.RLock dropped that method in Python 3.12, causing AttributeError
    on process exit. Replace _stop_locked with an identical copy that guards the
    call. All external refs are bound as default args so the function stays valid
    during interpreter shutdown when module globals are set to None."""
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


_patch_multiprocess_resource_tracker()


def pytest_configure() -> None:
    os.environ.setdefault("ENABLE_SEARCH_CACHE", "false")
    os.environ.setdefault("ENABLE_EMBEDDING_CACHE", "false")
    os.environ.setdefault("ENABLE_CROSS_ENCODER_RERANKING", "false")
