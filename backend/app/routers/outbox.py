from fastapi import APIRouter, Depends, HTTPException, status

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.outbox.models import OutboxJob
from app.outbox.service import OutboxService, get_outbox_service


router = APIRouter(tags=["outbox"])

OUTBOX_JOB_STATUSES: tuple[str, ...] = (
    "pending",
    "processing",
    "succeeded",
    "failed",
)


@router.get("/projects/{project_id}/outbox-jobs", response_model=list[OutboxJob])
def list_outbox_jobs(
    project_id: str,
    job_status: str | None = None,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[OutboxJob]:
    require_project(project_id, data_store)
    if job_status is not None and job_status not in OUTBOX_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown outbox job status. Expected one of: {', '.join(OUTBOX_JOB_STATUSES)}."
            ),
        )
    filtered = job_status
    return data_store.list_outbox_jobs(project_id, job_status=filtered)  # type: ignore[arg-type]


@router.post(
    "/projects/{project_id}/outbox-jobs/{job_id}/retry",
    response_model=OutboxJob,
)
def retry_outbox_job(
    project_id: str,
    job_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    outbox: OutboxService = Depends(get_outbox_service),
) -> OutboxJob:
    require_project(project_id, data_store)
    try:
        retried = outbox.retry(project_id, job_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if retried is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outbox job not found.",
        )
    return retried
