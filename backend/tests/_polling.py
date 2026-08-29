"""Shared polling helper for tests that assert asynchronous outcomes.

P1-03 dispatches outbox jobs outside the HTTP request path, so tests that
depend on post-commit side effects must wait for them instead of reading
state immediately after a mutation returns.
"""

import time


def wait_until(predicate, *, timeout_seconds: float = 15.0, message: str = "condition"):
    """Poll predicate() until truthy; raise AssertionError with last value."""
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.05)
    raise AssertionError(
        f"Timed out after {timeout_seconds}s waiting for {message}; "
        f"last value: {last!r}"
    )
