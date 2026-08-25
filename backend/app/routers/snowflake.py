from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.agents import (
    DeepSeekSettings,
    LocalDraftWritingWorkflow,
    WorkflowNotConfiguredError,
    WorkflowProviderError,
    WritingWorkflow,
    create_deepseek_workflow,
)
from app.data import WritingDataStore, get_data_store
from app.data.mixins.scene_proposals import (
    SceneChapterMissingError,
    SceneProposalNotFoundError,
    SceneProposalReviewedError,
    SceneSequenceConflictError,
)
from app.dependencies import require_project
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import LlmWiki, WikiSourceDocument
from app.outbox.handlers import snowflake_index_payload
from app.outbox.http import apply_wiki_index_headers
from app.outbox.service import OutboxService, get_outbox_service
from app.models import (
    CanonExtractionReport,
    SceneParseReport,
    SceneProposal,
    SceneProposalAcceptanceReport,
    SceneProposalAcceptRequest,
    SceneProposalStatusUpdate,
    SnowflakeArtifact,
    SnowflakeArtifactUpdate,
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeStep,
    WorkflowRuntimeStatus,
)
from app.services.snowflake_compile_service import SnowflakeCompileService
from app.snowflake_compiler import CANON_EXTRACT_STEP, SCENE_PARSE_STEP, ArtifactNotParseableError


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


@router.get("/snowflake/workflow/status", response_model=WorkflowRuntimeStatus)
def get_workflow_runtime_status() -> WorkflowRuntimeStatus:
    try:
        settings = DeepSeekSettings.from_env()
    except ValueError as exc:
        return WorkflowRuntimeStatus(
            runtime="local_deterministic",
            provider="local",
            provider_configured=False,
            details=f"DeepSeek environment is invalid: {exc}",
        )
    if settings is None:
        return WorkflowRuntimeStatus(
            runtime="local_deterministic",
            provider="local",
            provider_configured=False,
            details="DEEPSEEK_API_KEY is not configured; using deterministic local drafts.",
        )
    return WorkflowRuntimeStatus(
        runtime="provider_deepseek",
        provider="deepseek",
        provider_configured=True,
        model=settings.model,
        base_url=settings.base_url,
        details="DeepSeek provider runtime is configured for Snowflake draft generation.",
    )


def get_snowflake_step(step_number: int) -> SnowflakeStep:
    for step in SNOWFLAKE_STEPS:
        if step.number == step_number:
            return step
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Snowflake step not found.",
    )


@router.get(
    "/projects/{project_id}/snowflake/artifacts",
    response_model=list[SnowflakeArtifact],
)
def list_snowflake_artifacts(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[SnowflakeArtifact]:
    require_project(project_id, data_store)
    return data_store.list_snowflake_artifacts(project_id)


@router.get(
    "/projects/{project_id}/snowflake/artifacts/{step_number}",
    response_model=SnowflakeArtifact,
)
def get_snowflake_artifact(
    project_id: str,
    step_number: int,
    data_store: WritingDataStore = Depends(get_data_store),
) -> SnowflakeArtifact:
    require_project(project_id, data_store)
    get_snowflake_step(step_number)
    artifact = data_store.get_snowflake_artifact(project_id, step_number)
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
    response: Response,
    data_store: WritingDataStore = Depends(get_data_store),
    outbox: OutboxService = Depends(get_outbox_service),
) -> SnowflakeArtifact:
    require_project(project_id, data_store)
    step = get_snowflake_step(step_number)
    artifact = SnowflakeArtifact(
        project_id=project_id,
        step_number=step_number,
        artifact=step.artifact,
        content=update.content,
    )
    # One transaction: artifact + project step + index job.
    saved, job_id = data_store.enqueue_snowflake_index_job(artifact, advance_step_to=step_number)
    processed = outbox.process_job(project_id, job_id)
    if processed is not None:
        apply_wiki_index_headers(response, [processed])
    return saved


def get_writing_workflow(
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> WritingWorkflow:
    try:
        deepseek_workflow = create_deepseek_workflow(
            data_store,
            SNOWFLAKE_STEPS,
            llm_wiki,
        )
    except ValueError:
        deepseek_workflow = None
    if deepseek_workflow is not None:
        return deepseek_workflow
    return LocalDraftWritingWorkflow(data_store, SNOWFLAKE_STEPS, llm_wiki)


@router.post(
    "/snowflake/generate",
    response_model=SnowflakeGenerationResponse,
)
def generate_snowflake_artifact(
    request: SnowflakeGenerationRequest,
    response: Response,
    data_store: WritingDataStore = Depends(get_data_store),
    workflow: WritingWorkflow = Depends(get_writing_workflow),
    outbox: OutboxService = Depends(get_outbox_service),
) -> SnowflakeGenerationResponse:
    require_project(request.project_id, data_store)
    get_snowflake_step(request.step_number)
    try:
        generated = workflow.run_snowflake_generation(request)
    except WorkflowNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "message": str(exc),
                "workflow_trace": [trace.model_dump() for trace in exc.trace],
            },
        ) from exc
    except WorkflowProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(exc),
                "workflow_trace": [trace.model_dump() for trace in exc.trace],
            },
        ) from exc
    # One transaction: artifact + project step + index job.
    _, job_id = data_store.enqueue_snowflake_index_job(
        SnowflakeArtifact(
            project_id=generated.project_id,
            step_number=generated.step_number,
            artifact=generated.artifact,
            content=generated.content,
        ),
        advance_step_to=request.step_number,
    )
    processed = outbox.process_job(request.project_id, job_id)
    if processed is not None:
        apply_wiki_index_headers(response, [processed])
    return generated


def snowflake_wiki_document(artifact: SnowflakeArtifact) -> WikiSourceDocument:
    """Kept for compatibility; the mapping now lives in app.outbox.handlers."""
    return WikiSourceDocument.model_validate(snowflake_index_payload(artifact))


# ---------------------------------------------------------------------------
# Structured compiler (P1-05): artifacts -> reviewable proposals
# ---------------------------------------------------------------------------


def get_snowflake_compile_service(
    data_store: WritingDataStore = Depends(get_data_store),
) -> SnowflakeCompileService:
    return SnowflakeCompileService(data_store)


def unprocessable_artifact(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc),
    )


@router.post(
    ("/projects/{project_id}/snowflake/artifacts/{step_number}/compile-canon-proposals"),
    response_model=CanonExtractionReport,
    status_code=status.HTTP_201_CREATED,
)
def compile_canon_proposals_from_artifact(
    project_id: str,
    step_number: int,
    force: bool = False,
    data_store: WritingDataStore = Depends(get_data_store),
    service: SnowflakeCompileService = Depends(get_snowflake_compile_service),
) -> CanonExtractionReport:
    """Step 7 artifact -> Canon create / update write-back proposals."""
    require_project(project_id, data_store)
    if step_number != CANON_EXTRACT_STEP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Canon extraction compiles Snowflake step 7 artifacts; "
                f"step {step_number} is not compilable into Canon proposals."
            ),
        )
    try:
        return service.extract_canon_proposals(project_id, step_number, force=force)
    except ArtifactNotParseableError as exc:
        raise unprocessable_artifact(exc) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    ("/projects/{project_id}/snowflake/artifacts/{step_number}/parse-scene-proposals"),
    response_model=SceneParseReport,
    status_code=status.HTTP_201_CREATED,
)
def parse_scene_proposals_from_artifact(
    project_id: str,
    step_number: int,
    force: bool = False,
    data_store: WritingDataStore = Depends(get_data_store),
    service: SnowflakeCompileService = Depends(get_snowflake_compile_service),
) -> SceneParseReport:
    """Step 8 artifact -> structured Scene Contract proposals."""
    require_project(project_id, data_store)
    if step_number != SCENE_PARSE_STEP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Scene parsing compiles Snowflake step 8 artifacts; "
                f"step {step_number} is not compilable into scene proposals."
            ),
        )
    try:
        return service.parse_scene_proposals(project_id, step_number, force=force)
    except ArtifactNotParseableError as exc:
        raise unprocessable_artifact(exc) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/projects/{project_id}/snowflake/scene-proposals",
    response_model=list[SceneProposal],
)
def list_scene_proposals(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    service: SnowflakeCompileService = Depends(get_snowflake_compile_service),
) -> list[SceneProposal]:
    require_project(project_id, data_store)
    return service.list_scene_proposals(project_id)


@router.put(
    "/projects/{project_id}/snowflake/scene-proposals/{proposal_id}/status",
    response_model=SceneProposal,
)
def update_scene_proposal_status(
    project_id: str,
    proposal_id: str,
    update: SceneProposalStatusUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
    service: SnowflakeCompileService = Depends(get_snowflake_compile_service),
) -> SceneProposal:
    require_project(project_id, data_store)
    try:
        proposal = service.update_scene_proposal_status(project_id, proposal_id, update.status)
    except ValueError as exc:
        # Illegal review transitions share the unified 409 semantics.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene proposal not found.",
        )
    return proposal


@router.post(
    "/projects/{project_id}/snowflake/scene-proposals/accept",
    response_model=SceneProposalAcceptanceReport,
)
def accept_scene_proposals(
    project_id: str,
    request: SceneProposalAcceptRequest | None = None,
    data_store: WritingDataStore = Depends(get_data_store),
    service: SnowflakeCompileService = Depends(get_snowflake_compile_service),
) -> SceneProposalAcceptanceReport:
    """Batch-accept parsed scene proposals into scene contracts.

    Empty proposal_ids accepts every pending proposal. The whole batch is
    created in one transaction; a single conflict rolls everything back.
    """
    require_project(project_id, data_store)
    requested_ids = request.proposal_ids if request is not None else []
    if not requested_ids:
        requested_ids = [
            proposal.id
            for proposal in service.list_scene_proposals(project_id)
            if proposal.status == "pending_review"
        ]
    try:
        scenes, proposals = service.accept_scene_proposals(project_id, requested_ids)
    except SceneProposalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except SceneChapterMissingError as exc:
        raise unprocessable_artifact(exc) from exc
    except (SceneProposalReviewedError, SceneSequenceConflictError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return SceneProposalAcceptanceReport(
        project_id=project_id,
        scenes=scenes,
        proposals=proposals,
    )
