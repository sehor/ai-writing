"""HTTP helpers that surface wiki index outcomes without changing bodies."""

from fastapi import Response

from app.outbox.models import OutboxJob

WIKI_INDEX_FAILED_MESSAGE = (
    "Core data saved; LLM Wiki indexing failed. "
    "The outbox job can be retried without duplicating data."
)


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
