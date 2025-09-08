

from backend.config.media_config import media_settings
import asyncio
from typing import Any, Dict


tasks_queue: asyncio.Queue[Dict[str, Any]] = None
tasks_executor: asyncio.Task | None = None
task_workers=[]

# -------------------------------------------------------------
thumbgen_tasks_qu:asyncio.Queue[Dict[str, Any]]=asyncio.Queue()
log_analytics_qu:asyncio.Queue[Dict[str, Any]]=asyncio.Queue()
notify_admin_qu:asyncio.Queue[Dict[str, Any]]=asyncio.Queue()

queue_dict={"thumbgen":thumbgen_tasks_qu,"log_analytics":log_analytics_qu,"notify_admin":notify_admin_qu}

