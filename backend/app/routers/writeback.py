import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.agents import (
    DeepSeekSettings,
    HermesAgentClient,
    WorkflowNotConfiguredError,
    build_provider_writeback_proposals,
)
from app.agents.writeback_workflow import validate_writeback_payload
from app.cognition.interfaces import CommittedContentEvent
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.models import (
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatusUpdate,
    HermesRevisionProcessResponse,
)


router = APIRouter(tags=["writeback"])


@router.get(
    "/projects/{project_id}/writeback/proposals",
    response_model=list[WritebackProposal],
)
def list_writeback_proposals(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[WritebackProposal]:
    require_project(project_id, data_store)
    return data_store.list_writeback_proposals(project_id)


@router.post(
    "/projects/{project_id}/writeback/proposals",
    response_model=WritebackProposal,
    status_code=status.HTTP_201_CREATED,
)
def create_writeback_proposal(
    project_id: str,
    proposal: WritebackProposalCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> WritebackProposal:
    require_project(project_id, data_store)
    return data_store.create_writeback_proposal(project_id, proposal)


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}",
    response_model=list[WritebackProposal],
    status_code=status.HTTP_201_CREATED,
)
def create_writeback_proposals_from_revision(
    project_id: str,
    revision_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> list[WritebackProposal]:
    require_project(project_id, data_store)
    revision = data_store.get_manuscript_revision(project_id, revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        )

    snapshot = build_project_snapshot(project_id, data_store)
    reports = cognition.ingest_committed_content(
        snapshot,
        CommittedContentEvent(
            source="manuscript_revision",
            source_ref=f"manuscript_revision:{revision.id}",
            title=revision.title,
            content=revision.content,
            revision=revision,
        ),
    )
    proposals = [
        proposal
        for report in reports
        for proposal in report.writeback_proposals
    ]
    return data_store.create_writeback_proposals(project_id, proposals)


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}/hermes",
    response_model=HermesRevisionProcessResponse,
    status_code=status.HTTP_201_CREATED,
)
def process_revision_with_hermes(
    project_id: str,
    revision_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> HermesRevisionProcessResponse:
    require_project(project_id, data_store)
    revision = data_store.get_manuscript_revision(project_id, revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        )
    scene = data_store.get_scene_contract(project_id, revision.scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found for manuscript revision.",
        )
    project = data_store.get_project(project_id)
    project_title = project.title if project else project_id

    result = HermesAgentClient().process_manuscript_revision(
        project_id=project_id,
        project_title=project_title,
        revision=revision,
        scene_contract=scene,
    )
    for proposal in result.writeback_proposals:
        validate_writeback_payload(proposal)
    stored_proposals = data_store.create_writeback_proposals(project_id, result.writeback_proposals)
    return HermesRevisionProcessResponse(
        status=result.status,
        summary=result.summary,
        wiki_changes=result.wiki_changes,
        issues=result.issues,
        writeback_proposals=stored_proposals,
        processed_source_ref=result.processed_source_ref,
    )


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}/provider",
    response_model=list[WritebackProposal],
    status_code=status.HTTP_201_CREATED,
)
def create_provider_writeback_proposals_from_revision(
    project_id: str,
    revision_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[WritebackProposal]:
    require_project(project_id, data_store)
    revision = data_store.get_manuscript_revision(project_id, revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        )

    try:
        settings = DeepSeekSettings.from_env()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"DeepSeek env invalid: {exc}",
        ) from exc
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="DeepSeek provider is not configured.",
        )

    try:
        proposals = build_provider_writeback_proposals(
            settings,
            revision,
            data_store.list_canon_entities(project_id),
            data_store.list_memory_records(project_id),
        )
    except WorkflowNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider returned invalid write-back proposals: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provider write-back generation failed: {exc}",
        ) from exc

    return data_store.create_writeback_proposals(project_id, proposals)


@router.put(
    "/projects/{project_id}/writeback/proposals/{proposal_id}/status",
    response_model=WritebackProposal,
)
def update_writeback_proposal_status(
    project_id: str,
    proposal_id: str,
    update: WritebackProposalStatusUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> WritebackProposal:
    require_project(project_id, data_store)
    try:
        proposal = data_store.update_writeback_proposal_status(
            project_id,
            proposal_id,
            update.status,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Write-back payload does not match the target record shape.",
        ) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Accepted write-back would duplicate an existing record.",
        ) from exc
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Write-back proposal not found.",
        )
    return proposal
