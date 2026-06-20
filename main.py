"""FastAPI application entry point."""

import logging

import uvicorn
from dotenv import load_dotenv

from src.observability.logging import patch_multiprocess_resource_tracker, setup_logging

# Patch before anything imports multiprocess (RAGAS/datasets), then style logs.
patch_multiprocess_resource_tracker()
load_dotenv()
setup_logging()

from src.api.server import app  # noqa: E402  (after logging is configured)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logger.info("╭─────────────────────────────────────────────────────────╮")
    logger.info("│  ATLAS · Agentic Task & Literature Analysis System        │")
    logger.info("│  http://127.0.0.1:8000                                     │")
    logger.info("╰─────────────────────────────────────────────────────────╯")

    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
