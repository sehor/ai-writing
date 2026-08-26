"""Structured runtime observability (P2-08).

Every operational event is one JSON line on stdout through the standard
``logging`` machinery. The stable field set matches the improvement plan:
``request_id``, ``operation``, ``project_id``, ``aggregate_id``,
``provider``, ``duration_ms``, ``result`` and ``error_code``; anything else
an event wants to carry rides in explicit extra fields.

Policy: never log API keys or full prose content. Callers pass identifiers,
counts and durations only.
"""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Iterator

from app.data.helpers import utc_now

_LOGGER = logging.getLogger("ai_writing.ops")
if not _LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(_handler)
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def current_request_id() -> str:
    return _request_id.get()


def bind_request_id(request_id: str) -> None:
    """Bind the request id for the current execution context."""
    _request_id.set(request_id)


def log_event(event: str, **fields: object) -> None:
    """Emit one JSON line; empty/None fields are omitted entirely."""
    payload: dict[str, object] = {
        "ts": utc_now(),
        "event": event,
        "request_id": current_request_id(),
    }
    for key, value in fields.items():
        if value is not None and value != "":
            payload[key] = value
    _LOGGER.info(json.dumps(payload, ensure_ascii=False))


@contextmanager
def timed_operation(
    event: str,
    *,
    operation: str = "",
    project_id: str = "",
    aggregate_id: str = "",
    provider: str = "",
) -> Iterator[dict[str, object]]:
    """Log ``event`` with duration/result/error_code around a block."""
    details: dict[str, object] = {}
    started = time.perf_counter()
    try:
        yield details
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            event,
            operation=operation,
            project_id=project_id,
            aggregate_id=aggregate_id,
            provider=provider,
            duration_ms=duration_ms,
            result="error",
            error_code=type(exc).__name__,
            **details,
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            event,
            operation=operation,
            project_id=project_id,
            aggregate_id=aggregate_id,
            provider=provider,
            duration_ms=duration_ms,
            result=str(details.pop("result", "ok")),
            error_code="",
            **details,
        )
