from fastapi import APIRouter, Depends, status

from app.data import WritingDataStore, get_data_store
from app.models import ProjectCreate, ProjectSummary


router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[ProjectSummary]:
    return data_store.list_projects()


@router.post(
    "/projects",
    response_model=ProjectSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    project: ProjectCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> ProjectSummary:
    return data_store.create_project(project)
