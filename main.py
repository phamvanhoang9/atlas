"""FastAPI application entry point."""

import logging

import uvicorn
from dotenv import load_dotenv

from src.api.server import app


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("ATLAS - Agentic Task & Literature Analysis System")
    logger.info("=" * 70)

    uvicorn.run(app, host="127.0.0.1", port=8000)
