"""App-owned Outbox Dispatcher (P1-03).

Runs post-commit side-effect jobs OUTSIDE any HTTP request: a mutation only
commits core data and wakes this loop, which claims pending jobs through the
P1-02 compare-and-set and executes their handlers on worker threads.

Local-first constraints honoured here:

- single process, no external broker (Redis/Celery/Kafka);
- reuses ``OutboxService`` claim/retry/recovery semantics unchanged;
- every job left 'pending' or with an expired processing lease by a previous
  crash is consumed automatically on startup (first sweep);
- shutdown stops claiming new work and bounded-waits the current sweep; a job
  interrupted mid-handler stays 'processing' with its lease stamp and is
  recovered by the stale-lease sweep later.

The handlers themselves are synchronous, so each sweep runs inside
``asyncio.to_thread`` to keep the event loop responsive.
"""

import asyncio
import threading
from typing import Callable

from fastapi import Request

from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.data import WritingDataStore, get_data_store
from app.integrations.llmwiki_clp import get_knowledge_compiler
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import LlmWiki
from app.observability import log_event
from app.outbox.models import OutboxJob
from app.outbox.service import DEFAULT_PROCESSING_LEASE_SECONDS, OutboxService

# How often the loop sweeps on its own when nobody signals new work. Wake
# signals make enqueue-to-execution latency independent of this interval.
DEFAULT_POLL_INTERVAL_SECONDS = 1.0

# Bounded wait for the in-flight sweep during application shutdown before the
# loop task is cancelled; anything left behind stays recoverable (see module
# docstring).
DEFAULT_STOP_TIMEOUT_SECONDS = 10.0


class OutboxDispatcher:
    """Background asyncio loop that drains pending outbox jobs."""

    def __init__(
        self,
        service: OutboxService,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        lease_seconds: int = DEFAULT_PROCESSING_LEASE_SECONDS,
        stop_timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS,
    ):
        self.service = service
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._stop_timeout_seconds = stop_timeout_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake_event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        # stop() may be requested from another thread than the loop's.
        self._stopping = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the dispatch loop on the running event loop (idempotent)."""
        if self._task is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._wake_event = asyncio.Event()
        self._stopping.clear()
        # Sweep immediately so leftover pending / stale-processing jobs from
        # a crashed predecessor are consumed right after startup.
        self._wake_event.set()
        self._task = self._loop.create_task(self._run_loop(), name="outbox-dispatcher")

    async def stop(self, timeout_seconds: float | None = None) -> None:
        """Stop claiming new jobs; bounded-wait the current sweep."""
        if self._task is None:
            return
        self._stopping.set()
        timeout = self._stop_timeout_seconds if timeout_seconds is None else timeout_seconds
        self._wake_event.set()
        task = self._task
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except TimeoutError:
            # Leave the recoverable state in place instead of blocking
            # shutdown forever: an abandoned handler keeps its lease stamp
            # and is reset by the stale-lease recovery of the next start.
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        finally:
            self._task = None
            self._loop = None
            self._wake_event = None

    def wake(self) -> None:
        """Signal that new jobs were enqueued; safe from any thread."""
        loop = self._loop
        event = self._wake_event
        if loop is None or event is None or not loop.is_running():
            return
        loop.call_soon_threadsafe(event.set)

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def loop_task(self) -> asyncio.Task | None:
        return self._task

    # ------------------------------------------------------------------
    # Dispatching
    # ------------------------------------------------------------------

    async def dispatch_once(self) -> list[OutboxJob]:
        """Run exactly one sweep; also usable without a running loop."""
        return await self._sweep()

    async def _run_loop(self) -> None:
        assert self._wake_event is not None
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=self._poll_interval_seconds)
            except TimeoutError:
                pass
            self._wake_event.clear()
            if self._stopping.is_set():
                break
            await self._sweep()

    async def _sweep(self) -> list[OutboxJob]:
        service = self.service
        # 1. Reset leases whose worker died mid-handler (crash recovery).
        await asyncio.to_thread(
            service.recover_stale_processing_jobs, lease_seconds=self._lease_seconds
        )
        # 2. Drain everything currently pending, one claim at a time.
        processed = await asyncio.to_thread(service.resume_pending_jobs)
        return processed


def wake_outbox_best_effort(
    dispatcher: OutboxDispatcher,
    *,
    operation: str,
    project_id: str,
) -> None:
    """Wake derived post-commit work without invalidating an authoritative commit."""
    try:
        dispatcher.wake()
    except Exception as exc:
        log_event(
            "outbox_wake",
            operation=operation,
            project_id=project_id,
            result="error",
            error_code=type(exc).__name__,
        )


def get_outbox_dispatcher(request: Request) -> OutboxDispatcher:
    """FastAPI dependency handing out the lifespan-owned dispatcher."""
    dispatcher: OutboxDispatcher = request.app.state.outbox_dispatcher
    return dispatcher


def build_app_outbox_dispatcher(app) -> OutboxDispatcher:
    """Create the dispatcher from the same providers HTTP routes resolve.

    Dependency overrides registered on the app (used by the test suite) are
    honoured, so tests drive the real background loop against their temporary
    stores instead of the process-wide default instances.
    """

    def resolve(dependency: Callable):
        override = app.dependency_overrides.get(dependency)
        if override is not None:
            return override()
        return dependency()

    data_store: WritingDataStore = resolve(get_data_store)
    wiki: LlmWiki = resolve(get_llm_wiki)
    cognition: CognitionRegistry = resolve(get_cognition_registry)
    compiler = get_knowledge_compiler()
    service = OutboxService(
        data_store=data_store,
        wiki=wiki,
        cognition=cognition,
        compiler=compiler,
    )
    return OutboxDispatcher(service)
