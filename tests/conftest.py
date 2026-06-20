import os

# Disable caches/reranking BEFORE importing anything from `src`: `src/__init__`
# eagerly imports the orchestration + config stack, which reads these env vars at
# import time. Setting them here (not just in pytest_configure) guarantees the
# defaults win even though the import below pulls in `src`.
os.environ.setdefault("ENABLE_SEARCH_CACHE", "false")
os.environ.setdefault("ENABLE_EMBEDDING_CACHE", "false")
os.environ.setdefault("ENABLE_CROSS_ENCODER_RERANKING", "false")

from src.observability.logging import patch_multiprocess_resource_tracker  # noqa: E402

# Apply the Python 3.12 multiprocess RLock guard before tests import multiprocess
# (RAGAS/datasets). Shared with the runtime path in src/observability/logging.py.
patch_multiprocess_resource_tracker()


def pytest_configure() -> None:
    os.environ.setdefault("ENABLE_SEARCH_CACHE", "false")
    os.environ.setdefault("ENABLE_EMBEDDING_CACHE", "false")
    os.environ.setdefault("ENABLE_CROSS_ENCODER_RERANKING", "false")
