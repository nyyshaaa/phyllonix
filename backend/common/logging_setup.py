import logging
import sys
import json
import re
from typing import Any, Dict, Optional
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from backend.config.admin_config import admin_config
from backend.common.constants import request_id_ctx

ENV = getattr(admin_config, "ENV", "dev").lower()


def sanitize_message_text(msg: str) -> str:
    """Sanitize sensitive patterns inside a text message (best-effort)."""
    SENSITIVE_PATTERNS = [
        r"password", r"secret", r"token", r"key", r"authorization",
        r"api_key", r"apikey", r"access_token", r"refresh_token",
        r"credit_card", r"cvv", r"ssn", r"pwd_hash"
    ]
    out = msg
    for p in SENSITIVE_PATTERNS:
        # replace occurrences like "password=abc" or '"password": "abc"'
        out = re.sub(rf'("{p}"\s*:\s*")[^"]+(")', rf'\1[REDACTED]\2', out, flags=re.IGNORECASE)
        out = re.sub(rf'({p}\s*[=:\s]\s*)[\w\-\./]+', rf'\1[REDACTED]', out, flags=re.IGNORECASE)
    return out


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for production"""
    def format(self, record: logging.LogRecord) -> str:
        # base fields
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "env": ENV,
            "service": getattr(admin_config, "SERVICE_NAME", "phyllonix"),
        }

        # contextvars: request_id, trace_id
        rid = request_id_ctx.get()
        if rid:
            log_data["request_id"] = rid

        # record.extra if present (stdlib uses record.__dict__)
        extra_fields = {}
        for k, v in record.__dict__.items():
            if k in ("name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                     "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                     "created", "msecs", "relativeCreated", "thread", "threadName", "processName",
                     "process"):
                continue
            if k.startswith("_"):
                continue
            extra_fields[k] = v

        # sanitize in production: show first 8 chars only
        for field in ["user_public_id", "public_id", "device_public_id"]:
            if field in extra_fields:
                if ENV != "dev":
                    try:
                        val = str(extra_fields[field])
                        if len(val) > 12:  # UUID is typically 36 chars
                            extra_fields[field] = val[:8] + "..." + val[-4:]
                        else:
                            extra_fields[field] = val[:8] + "..."
                    except Exception:
                        extra_fields[field] = "[REDACTED]"
        # merge extras
        log_data.update(extra_fields)

        # exception formatting
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # final sanitization at message-level in prod
        if ENV != "dev":
            log_data["message"] = sanitize_message_text(log_data.get("message", ""))

        return json.dumps(log_data, default=str)


class SecurityFilter(logging.Filter):
    """Filter out or redact sensitive info in production logs"""
    SENSITIVE_PATTERNS = [
        "password", "secret", "token", "key", "authorization",
        "api_key", "access_token", "refresh_token",
        "credit_card", "cvv", "ssn", "pwd_hash"
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        # Sanitize msg text (best-effort)
        try:
            msg = record.getMessage()
            if ENV != "dev":
                # redact any obvious patterns in the message string
                record.msg = sanitize_message_text(msg)
                record.args = ()
        except Exception:
            pass
        return True


# Set up a non-blocking queue-based logger. Use once at app startup.
_queue_listener: Optional[QueueListener] = None


def setup_logging():
   
    global _queue_listener

    # choose log level
    if ENV == "prod":
        log_level = logging.INFO
    elif ENV == "staging":
        log_level = logging.INFO
    else:
        log_level = logging.DEBUG

    root = logging.getLogger()
    # Clear existing handlers to avoid duplication
    for h in list(root.handlers):
        root.removeHandler(h)

    # Create queue and queue handler for non-blocking behaviour
    q: Queue = Queue(-1)
    qh = QueueHandler(q)

    # Console handler writes to stdout (the queue listener will handle it)
    console_handler = logging.StreamHandler(sys.stdout)
    if ENV != "dev":
        console_handler.setFormatter(JSONFormatter())
        console_handler.addFilter(SecurityFilter())
    else:
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)8s] %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))

    # attach queue handler to root
    root.setLevel(log_level)
    root.addHandler(qh)

    # Start a QueueListener to consume log records and write to console_handler
    _queue_listener = QueueListener(q, console_handler, respect_handler_level=True)
    _queue_listener.start()

    # silence noisy third-party loggers in prod
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING if ENV != "dev" else logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING if ENV != "dev" else logging.INFO)

    app_logger = logging.getLogger("chlorophyll.app")
    return app_logger


class ContextLogger:
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _with_ctx(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        extra = dict(extra or {})
        # attach request/trace from contextvars (they will be included by JSONFormatter)
        rid = request_id_ctx.get()
        if rid:
            extra.setdefault("request_id", rid)

        return extra

    def debug(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", {})
        kwargs["extra"] = {**self._with_ctx(), **(extra or {})}
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", {})
        kwargs["extra"] = {**self._with_ctx(), **(extra or {})}
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", {})
        kwargs["extra"] = {**self._with_ctx(), **(extra or {})}
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", {})
        kwargs["extra"] = {**self._with_ctx(), **(extra or {})}
        self._logger.error(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        extra = kwargs.pop("extra", {})
        kwargs["extra"] = {**self._with_ctx(), **(extra or {})}
        self._logger.exception(msg, *args, **kwargs)


def get_logger(name: str = "chlorophyll.app") -> ContextLogger:
    return ContextLogger(name)
