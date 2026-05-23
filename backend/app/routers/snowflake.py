from fastapi import APIRouter, Depends, HTTPException, status

from app.agents import (
    InterfaceOnlyWritingWorkflow,
    WorkflowNotConfiguredError,
    WritingWorkflow,
)
from app.models import (
    SnowflakeArtifact,
    SnowflakeArtifactUpdate,
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeStep,
)
from app.routers.projects import project_exists


router = APIRouter(tags=["snowflake"])

SNOWFLAKE_ARTIFACTS: dict[tuple[str, int], SnowflakeArtifact] = {}


SNOWFLAKE_STEPS = [
    SnowflakeStep(
        number=1,
        title="One Sentence",
        artifact="story_contract",
        description="Distill the novel into a single sentence promise.",
    ),
    SnowflakeStep(
        number=2,
        title="One Paragraph",
        artifact="plot_seed",
        description="Expand the story promise into a compact beginning, middle, and end.",
    ),
    SnowflakeStep(
        number=3,
        title="Character Summary",
        artifact="character_seeds",
        description="Create initial goals, conflicts, secrets, and arcs for major characters.",
    ),
    SnowflakeStep(
        number=4,
        title="One Page Synopsis",
        artifact="plot_synopsis",
        description="Compile the story into a one-page plot outline.",
    ),
    SnowflakeStep(
        number=5,
        title="Character Viewpoints",
        artifact="character_pov_lines",
        description="Describe the story from each major character's perspective.",
    ),
    SnowflakeStep(
        number=6,
        title="Expanded Synopsis",
        artifact="expanded_plot",
        description="Expand the plot into a multi-page causal outline.",
    ),
    SnowflakeStep(
        number=7,
        title="Character Bible",
        artifact="canon_entities",
        description="Commit character, location, item, and faction facts into Canon.",
    ),
    SnowflakeStep(
        number=8,
        title="Scene List",
        artifact="scene_contracts",
        description="Compile the plot into scene contracts with goals, conflicts, turns, and constraints.",
    ),
    SnowflakeStep(
        number=9,
        title="Scene Expansion",
        artifact="expanded_scenes",
        description="Expand each scene contract into detailed beats and chapter plans.",
    ),
    SnowflakeStep(
        number=10,
        title="Draft Manuscript",
        artifact="manuscript",
        description="Draft prose from scene contracts, Canon constraints, memory, and style samples.",
    ),
]


@router.get("/snowflake/steps", response_model=list[SnowflakeStep])
def list_snowflake_steps() -> list[SnowflakeStep]:
    return SNOWFLAKE_STEPS


def get_snowflake_step(step_number: int) -> SnowflakeStep:
    for step in SNOWFLAKE_STEPS:
        if step.number == step_number:
            return step
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Snowflake step not found.",
    )


def require_project(project_id: str) -> None:
    if not project_exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )


@router.get(
    "/projects/{project_id}/snowflake/artifacts",
    response_model=list[SnowflakeArtifact],
)
def list_snowflake_artifacts(project_id: str) -> list[SnowflakeArtifact]:
    require_project(project_id)
    artifacts = [
        artifact
        for (stored_project_id, _), artifact in SNOWFLAKE_ARTIFACTS.items()
        if stored_project_id == project_id
    ]
    return sorted(artifacts, key=lambda artifact: artifact.step_number)


@router.get(
    "/projects/{project_id}/snowflake/artifacts/{step_number}",
    response_model=SnowflakeArtifact,
)
def get_snowflake_artifact(project_id: str, step_number: int) -> SnowflakeArtifact:
    require_project(project_id)
    get_snowflake_step(step_number)
    artifact = SNOWFLAKE_ARTIFACTS.get((project_id, step_number))
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snowflake artifact not found.",
        )
    return artifact


@router.put(
    "/projects/{project_id}/snowflake/artifacts/{step_number}",
    response_model=SnowflakeArtifact,
)
def save_snowflake_artifact(
    project_id: str,
    step_number: int,
    update: SnowflakeArtifactUpdate,
) -> SnowflakeArtifact:
    require_project(project_id)
    step = get_snowflake_step(step_number)
    artifact = SnowflakeArtifact(
        project_id=project_id,
        step_number=step_number,
        artifact=step.artifact,
        content=update.content,
    )
    SNOWFLAKE_ARTIFACTS[(project_id, step_number)] = artifact
    return artifact


def get_writing_workflow() -> WritingWorkflow:
    return InterfaceOnlyWritingWorkflow()


@router.post(
    "/snowflake/generate",
    response_model=SnowflakeGenerationResponse,
)
def generate_snowflake_artifact(
    request: SnowflakeGenerationRequest,
    workflow: WritingWorkflow = Depends(get_writing_workflow),
) -> SnowflakeGenerationResponse:
    try:
        return workflow.run_snowflake_generation(request)
    except WorkflowNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "message": str(exc),
                "workflow_trace": [trace.model_dump() for trace in exc.trace],
            },
        ) from exc
