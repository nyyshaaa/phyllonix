

from backend.config.media_config import media_settings
import asyncio
from typing import Any, Dict


tasks_queue: asyncio.Queue[Dict[str, Any]] = None
tasks_executor: asyncio.Task | None = None
task_workers=[]