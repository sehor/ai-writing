from fastapi import APIRouter, Depends, HTTPException, status

from app.agents import AgentNotConfiguredError, UnconfiguredWritingAgent, WritingAgent
from app.models import (
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeStep,
)


router = APIRouter(tags=["snowflake"])


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


def get_writing_agent() -> WritingAgent:
    return UnconfiguredWritingAgent()


@router.post(
    "/snowflake/generate",
    response_model=SnowflakeGenerationResponse,
)
def generate_snowflake_artifact(
    request: SnowflakeGenerationRequest,
    agent: WritingAgent = Depends(get_writing_agent),
) -> SnowflakeGenerationResponse:
    try:
        return agent.generate_snowflake_artifact(request)
    except AgentNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
