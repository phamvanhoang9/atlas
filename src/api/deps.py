"""Shared API dependencies and runtime singletons."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, TypeVar

from fastapi.templating import Jinja2Templates

from src.automation.store import AutomationStore
from src.storage.history import SQLiteHistoryManager
from src.transport.manager import WebSocketManager

T = TypeVar("T")

history_manager = SQLiteHistoryManager(os.getenv("HISTORY_DB_PATH", ".atlas_data/history.sqlite"))
automation_store = AutomationStore(os.getenv("HISTORY_DB_PATH", ".atlas_data/history.sqlite"))
manager = WebSocketManager()
templates = Jinja2Templates(directory="./frontend")


async def run_sync(operation: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run sync storage/export work without blocking the event loop."""
    return await asyncio.to_thread(operation, *args, **kwargs)

