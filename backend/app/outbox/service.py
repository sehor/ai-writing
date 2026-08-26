"""Outbox dispatch: run pending side effects after the core transaction."""

import time

from fastapi import Depends

from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.data import WritingDataStore, get_data_store
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import LlmWiki
from app.observability import log_event
from app.outbox.handlers import OUTBOX_HANDLERS, OutboxJobContext
from app.outbox.models import OutboxJob


class OutboxService:
    def __init__(
        self,
        data_store: WritingDataStore,
        wiki: LlmWiki,
        cognition: CognitionRegistry | None = None,
    ):
        self.data_store = data_store
        self.wiki = wiki
        self.cognition = cognition

    def process_pending(self, project_id: str) -> list[OutboxJob]:
        """Run every pending job for a project; never raises.

        Each job transitions pending -> processing -> succeeded/failed.
        Handler exceptions are captured on the job itself so one bad job
        cannot block or crash the request that triggered it.
        """
        jobs = self.data_store.list_outbox_jobs(project_id, job_status="pending")
        return [self._run(job) for job in jobs]

    def process_job(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Run one specific job if it is still executable."""
        job = self.data_store.get_outbox_job(project_id, job_id)
        if job is None or job.status not in ("pending", "processing"):
            return job
        return self._run(job)

    def retry(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Re-run a failed job. Raises ValueError for non-failed jobs."""
        job = self.data_store.get_outbox_job(project_id, job_id)
        if job is None:
            return None
        if job.status != "failed":
            raise ValueError("Only failed outbox jobs can be retried.")
        reset = self.data_store.transition_outbox_job(project_id, job_id, job_status="pending")
        assert reset is not None  # row was just read successfully
        return self._run(reset)

    def _run(self, job: OutboxJob) -> OutboxJob:
        claimed = self.data_store.transition_outbox_job(
            job.project_id, job.id, job_status="processing"
        )
        if claimed is None:
            return job
        handler = OUTBOX_HANDLERS.get(job.job_type)
        context = OutboxJobContext(
            wiki=self.wiki,
            data_store=self.data_store,
            cognition=self.cognition,
        )
        started = time.perf_counter()
        try:
            if handler is None:
                raise ValueError(f"No handler registered for job type '{job.job_type}'.")
            handler(context, job.payload)
        except Exception as exc:  # isolate handler failures on the job record
            log_event(
                "outbox_job",
                operation=job.job_type,
                project_id=job.project_id,
                aggregate_id=f"{job.aggregate_type}:{job.aggregate_id}",
                attempt=claimed.attempt_count,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                result="failed",
                error_code=type(exc).__name__,
            )
            return (
                self.data_store.transition_outbox_job(
                    job.project_id,
                    job.id,
                    job_status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
                or claimed
            )
        log_event(
            "outbox_job",
            operation=job.job_type,
            project_id=job.project_id,
            aggregate_id=f"{job.aggregate_type}:{job.aggregate_id}",
            attempt=claimed.attempt_count,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            result="succeeded",
            error_code="",
        )
        return (
            self.data_store.transition_outbox_job(job.project_id, job.id, job_status="succeeded")
            or claimed
        )


def get_outbox_service(
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> OutboxService:
    return OutboxService(data_store=data_store, wiki=llm_wiki, cognition=cognition)
