"""Serialize restore and side effects in the supported single-process app.

SQLite transactions protect author writes. These reentrant locks keep background
handlers from writing stale files over a restored project. The registry contains
no story state, and unused locks are released automatically.
"""

from contextlib import contextmanager
from threading import Lock, RLock
from weakref import WeakValueDictionary

_registry_guard = Lock()
_operations: WeakValueDictionary = WeakValueDictionary()


@contextmanager
def project_operation(project_id: str):
    with _registry_guard:
        operation = _operations.get(project_id)
        if operation is None:
            operation = RLock()
            _operations[project_id] = operation
    with operation:
        yield
