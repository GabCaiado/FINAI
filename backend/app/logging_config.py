"""Structured JSON logs. Only whitelisted fields are emitted: request metadata, never
descriptions, amounts, prompts or credentials."""

import json
import logging
import sys
from datetime import UTC, datetime

from app.request_context import get_request_id

# Fields callers may attach via ``extra=``. Anything else is dropped on purpose.
ALLOWED_EXTRA = (
    "method",
    "path",
    "status",
    "duration_ms",
    "error_type",
    "error_at",
    "llm_rows",
    "llm_latency_ms",
    "llm_cache_hits",
    "llm_model",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": get_request_id(),
        }
        for key in ALLOWED_EXTRA:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # uvicorn's access log would print raw paths/queries; we log requests ourselves.
    logging.getLogger("uvicorn.access").disabled = True
