from re import sub

from fastapi import APIRouter, status

from app.models import ProjectCreate, ProjectSummary


router = APIRouter(tags=["projects"])

PROJECTS = [
    ProjectSummary(
        id="demo-novel",
        title="Demo Novel",
        premise="A prototype project for Snowflake-driven AI long-form writing.",
        current_step=1,
    )
]


def make_project_id(title: str) -> str:
    base = sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "project"
    existing_ids = {project.id for project in PROJECTS}
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    return PROJECTS


@router.post(
    "/projects",
    response_model=ProjectSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_project(project: ProjectCreate) -> ProjectSummary:
    created = ProjectSummary(
        id=make_project_id(project.title),
        title=project.title.strip(),
        premise=project.premise.strip(),
        current_step=1,
    )
    PROJECTS.append(created)
    return created
