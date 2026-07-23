import json
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

LOG_BUFFER: deque[dict[str, Any]] = deque(maxlen=500)


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            entry["request_id"] = record.request_id
        LOG_BUFFER.append(entry)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    buffer_handler = BufferHandler()
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.addHandler(buffer_handler)
    root_logger.setLevel(level.upper())


def recent_logs(level: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    normalized = level.upper() if level else None
    rows = [item for item in LOG_BUFFER if normalized is None or item["level"] == normalized]
    return list(reversed(rows[-limit:]))
