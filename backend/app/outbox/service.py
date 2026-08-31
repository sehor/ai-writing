"""Outbox dispatch: run pending side effects after the core transaction."""

import time
from datetime import UTC, datetime, timedelta

from fastapi import Depends
from app.data.project_operations import project_operation

from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.data import WritingDataStore, get_data_store
from app.llm_wiki.dependencies import get_llm_wiki
from app.integrations.knowledge_compiler import DisabledKnowledgeCompiler, KnowledgeCompiler
from app.integrations.llmwiki_clp import get_knowledge_compiler
from app.llm_wiki.interfaces import LlmWiki
from app.observability import log_event
from app.outbox.handlers import OUTBOX_HANDLERS, OutboxJobContext
from app.outbox.models import OutboxJob

# A 'processing' job whose lease stamp is older than this is considered
# abandoned by a crashed dispatcher and becomes recoverable again (P1-02).
DEFAULT_PROCESSING_LEASE_SECONDS = 600


class OutboxService:
    def __init__(
        self,
        data_store: WritingDataStore,
        wiki: LlmWiki,
        cognition: CognitionRegistry | None = None,
        compiler: KnowledgeCompiler | None = None,
    ):
        self.data_store = data_store
        self.wiki = wiki
        self.cognition = cognition
        self.compiler = compiler or DisabledKnowledgeCompiler()

    def process_pending(self, project_id: str) -> list[OutboxJob]:
        """Run every pending job for a project; never raises.

        Each job is claimed atomically before its handler runs, so a job
        taken by a concurrent dispatcher is skipped instead of re-executed.
        Handler exceptions are captured on the job itself so one bad job
        cannot block or crash the request that triggered it.
        """
        jobs = self.data_store.list_outbox_jobs(project_id, job_status="pending")
        return [self._run(job) for job in jobs]

    def process_job(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Run one specific job if it is still claimable."""
        job = self.data_store.get_outbox_job(project_id, job_id)
        if job is None or job.status != "pending":
            return job
        return self._run(job)

    def retry(self, project_id: str, job_id: str) -> OutboxJob | None:
        """Requeue a failed job; only the dispatcher executes its handler."""
        job = self.data_store.get_outbox_job(project_id, job_id)
        if job is None:
            return None
        if job.status != "failed":
            raise ValueError("Only failed outbox jobs can be retried.")
        reset = self.data_store.reset_failed_outbox_job(project_id, job_id)
        if reset is None:
            raise ValueError("Another request already retried this job.")
        return reset

    def resume_pending_jobs(self) -> list[OutboxJob]:
        """Process leftover pending jobs across every project.

        Crash recovery entry point: jobs enqueued right before a restart
        stay 'pending' and are finished here.
        """
        results: list[OutboxJob] = []
        for project_id in self.data_store.list_projects_with_pending_outbox_jobs():
            results.extend(self.process_pending(project_id))
        return results

    def recover_stale_processing_jobs(
        self, *, lease_seconds: int = DEFAULT_PROCESSING_LEASE_SECONDS
    ) -> list[OutboxJob]:
        """Reset 'processing' jobs whose lease expired back to pending."""
        cutoff = (datetime.now(UTC) - timedelta(seconds=lease_seconds)).isoformat(
            timespec="seconds"
        )
        return self.data_store.recover_stale_outbox_jobs(cutoff=cutoff)

    def recover_interrupted_jobs(
        self, *, lease_seconds: int = DEFAULT_PROCESSING_LEASE_SECONDS
    ) -> list[OutboxJob]:
        """One-call recovery after a restart: stale reset, then pending resume."""
        recovered = self.recover_stale_processing_jobs(lease_seconds=lease_seconds)
        return [*recovered, *self.resume_pending_jobs()]

    def _run(self, job: OutboxJob) -> OutboxJob:
        with project_operation(job.project_id):
            return self._run_locked(job)

    def _run_locked(self, job: OutboxJob) -> OutboxJob:
        claimed = self.data_store.claim_outbox_job(job.project_id, job.id)
        if claimed is None:
            # Lost the claim race, or the job reached a terminal state in
            # between: this dispatcher must not execute the handler.
            return job
        # A restore may have replaced this row while the sweep waited. Always
        # execute the freshly claimed payload, not the old sweep's snapshot.
        job = claimed
        handler = OUTBOX_HANDLERS.get(job.job_type)
        context = OutboxJobContext(
            wiki=self.wiki,
            data_store=self.data_store,
            cognition=self.cognition,
            compiler=self.compiler,
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
                self.data_store.complete_outbox_job(
                    job.project_id,
                    job.id,
                    succeeded=False,
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
            self.data_store.complete_outbox_job(job.project_id, job.id, succeeded=True) or claimed
        )


def get_outbox_service(
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> OutboxService:
    return OutboxService(
        data_store=data_store,
        wiki=llm_wiki,
        cognition=cognition,
        compiler=get_knowledge_compiler(),
    )
