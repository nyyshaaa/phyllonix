import contextvars
from typing import Optional
from backend.config.settings import config_settings
from backend.common.logging_setup import get_logger

logger = get_logger("chlorophyll.common")

NUM_CONSUMERS = 2

SESSION_TOKEN_COOKIE_MAX_AGE = config_settings.DEVICE_SESSION_EXPIRE_DAYS

# Context variables for request and trace id
request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
# trace_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)