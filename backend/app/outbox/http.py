"""HTTP helpers that surface post-commit job outcomes without changing bodies."""

from fastapi import Response

from app.outbox.models import OutboxJob

WIKI_INDEX_FAILED_MESSAGE = (
    "Core data saved; LLM Wiki indexing failed. "
    "The outbox job can be retried without duplicating data."
)

ANALYSIS_JOB_FAILED_MESSAGE = (
    "Core data saved; automatic analysis failed. "
    "The analysis job can be retried without duplicating data."
)

# Job types scheduled by P1-07 when a manuscript proposal is accepted.
POST_ACCEPT_ANALYSIS_JOB_TYPES = frozenset({"consistency_analysis", "writeback_analysis"})


def apply_wiki_index_headers(response: Response, jobs: list[OutboxJob]) -> None:
    """Record post-commit indexing results on the response headers."""
    if not jobs:
        return
    failed = [job for job in jobs if job.status == "failed"]
    if failed:
        response.headers["X-Wiki-Index-Status"] = "failed"
        response.headers["X-Wiki-Index-Job-Id"] = failed[0].id
        response.headers["X-Wiki-Index-Message"] = WIKI_INDEX_FAILED_MESSAGE
        return
    response.headers["X-Wiki-Index-Status"] = "succeeded"


def apply_post_accept_analysis_headers(response: Response, jobs: list[OutboxJob]) -> None:
    """Record post-acceptance analysis results on the response headers."""
    analysis_jobs = [job for job in jobs if job.job_type in POST_ACCEPT_ANALYSIS_JOB_TYPES]
    if not analysis_jobs:
        return
    failed = [job for job in analysis_jobs if job.status == "failed"]
    if failed:
        response.headers["X-Analysis-Job-Status"] = "failed"
        response.headers["X-Analysis-Job-Id"] = failed[0].id
        response.headers["X-Analysis-Job-Message"] = ANALYSIS_JOB_FAILED_MESSAGE
        return
    response.headers["X-Analysis-Job-Status"] = "succeeded"
