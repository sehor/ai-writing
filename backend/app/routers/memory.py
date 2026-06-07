from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.models import MemoryRecord, MemoryRecordCreate, MemoryRecordUpdate


router = APIRouter(tags=["memory"])


@router.get(
    "/projects/{project_id}/memory/records",
    response_model=list[MemoryRecord],
)
def list_memory_records(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[MemoryRecord]:
    require_project(project_id, data_store)
    return data_store.list_memory_records(project_id)


@router.post(
    "/projects/{project_id}/memory/records",
    response_model=MemoryRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_memory_record(
    project_id: str,
    record: MemoryRecordCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> MemoryRecord:
    require_project(project_id, data_store)
    return data_store.create_memory_record(project_id, record)


@router.put(
    "/projects/{project_id}/memory/records/{record_id}",
    response_model=MemoryRecord,
)
def update_memory_record(
    project_id: str,
    record_id: str,
    record: MemoryRecordUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> MemoryRecord:
    require_project(project_id, data_store)
    updated = data_store.update_memory_record(project_id, record_id, record)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory record not found.",
        )
    return updated


@router.delete(
    "/projects/{project_id}/memory/records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_memory_record(
    project_id: str,
    record_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> Response:
    require_project(project_id, data_store)
    deleted = data_store.delete_memory_record(project_id, record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory record not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
