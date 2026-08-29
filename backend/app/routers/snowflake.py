"""Pure HTTP layer for Snowflake routes.

Parses requests, delegates to application services, and maps domain
errors onto HTTP status codes. No provider runtime types are imported
here; workflow resolution happens behind the app-owned interface in
app.services.snowflake_service.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.agents.writing_workflow import (
    WorkflowNotConfiguredError,
    WorkflowProviderError,
    WritingWorkflow,
)
from app.data import WritingDataStore, get_data_store
from app.data.mixins.scene_proposals import (
    SceneChapterMissingError,
    SceneProposalNotFoundError,
    SceneProposalReviewedError,
    SceneSequenceConflictError,
)
from app.dependencies import require_project
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
from app.outbox.dispatcher import (
    OutboxDispatcher,
    get_outbox_dispatcher,
    wake_outbox_best_effort,
)
from app.services.snowflake_compile_service import SnowflakeCompileService

# Re-exported so tests can keep importing these symbols from the router.
from app.services.snowflake_service import (  # noqa: F401
    SNOWFLAKE_STEPS as SNOWFLAKE_STEPS,
    ArtifactNotFoundError as ArtifactNotFoundError,
    StepNotFoundError as StepNotFoundError,
    SnowflakeService as SnowflakeService,
    get_snowflake_service as get_snowflake_service,
    get_writing_workflow as get_writing_workflow,
    snowflake_wiki_document as snowflake_wiki_document,
)
from app.snowflake_compiler import CANON_EXTRACT_STEP, SCENE_PARSE_STEP, ArtifactNotParseableError


router = APIRouter(tags=["snowflake"])


@router.get("/snowflake/steps", response_model=list[SnowflakeStep])
def list_snowflake_steps() -> list[SnowflakeStep]:
    return SNOWFLAKE_STEPS


@router.get("/snowflake/workflow/status", response_model=WorkflowRuntimeStatus)
def get_workflow_runtime_status(
    service: SnowflakeService = Depends(get_snowflake_service),
) -> WorkflowRuntimeStatus:
    return service.runtime_status()


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
    service: SnowflakeService = Depends(get_snowflake_service),
) -> SnowflakeArtifact:
    require_project(project_id, data_store)
    try:
        return service.get_artifact(project_id, step_number)
    except StepNotFoundError as exc:
        raise not_found_step() from exc
    except ArtifactNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snowflake artifact not found.",
        ) from exc


@router.put(
    "/projects/{project_id}/snowflake/artifacts/{step_number}",
    response_model=SnowflakeArtifact,
)
def save_snowflake_artifact(
    project_id: str,
    step_number: int,
    update: SnowflakeArtifactUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
    service: SnowflakeService = Depends(get_snowflake_service),
    dispatcher: OutboxDispatcher = Depends(get_outbox_dispatcher),
) -> SnowflakeArtifact:
    require_project(project_id, data_store)
    try:
        saved, job_id = service.save_artifact(project_id, step_number, update.content)
    except StepNotFoundError as exc:
        raise not_found_step() from exc
    # P1-03: the index job was enqueued in the save transaction; the
    # background dispatcher owns its execution, not this request.
    if job_id:
        wake_outbox_best_effort(
            dispatcher,
            operation="snowflake_artifact_save",
            project_id=project_id,
        )
    return saved


@router.post(
    "/snowflake/generate",
    response_model=SnowflakeGenerationResponse,
)
def generate_snowflake_artifact(
    request: SnowflakeGenerationRequest,
    data_store: WritingDataStore = Depends(get_data_store),
    workflow: WritingWorkflow = Depends(get_writing_workflow),
    service: SnowflakeService = Depends(get_snowflake_service),
    dispatcher: OutboxDispatcher = Depends(get_outbox_dispatcher),
) -> SnowflakeGenerationResponse:
    require_project(request.project_id, data_store)
    try:
        generated, job_id = service.generate(request, workflow)
    except StepNotFoundError as exc:
        raise not_found_step() from exc
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
    # P1-03: indexing happens in the background dispatcher.
    if job_id:
        wake_outbox_best_effort(
            dispatcher,
            operation="snowflake_generation_save",
            project_id=request.project_id,
        )
    return generated


def not_found_step() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Snowflake step not found.",
    )


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
