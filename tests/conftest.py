import os


def pytest_configure() -> None:
    os.environ.setdefault("ENABLE_SEARCH_CACHE", "false")
    os.environ.setdefault("ENABLE_EMBEDDING_CACHE", "false")
    os.environ.setdefault("ENABLE_CROSS_ENCODER_RERANKING", "false")
