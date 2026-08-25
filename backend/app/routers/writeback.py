import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError

from app.agents import (
    DeepSeekSettings,
    HermesAgentClient,
    WorkflowNotConfiguredError,
    build_provider_writeback_proposals,
)
from app.analysis.http import apply_analysis_headers
from app.analysis.service import AnalysisService, writeback_input_fingerprint
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
from app.review.service import (
    WritebackPreValidationError,
    ensure_writeback_proposals_acceptable,
    unprocessable_from,
)


router = APIRouter(tags=["writeback"])


def get_analysis_service(
    data_store: WritingDataStore = Depends(get_data_store),
) -> AnalysisService:
    return AnalysisService(data_store=data_store)


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
    try:
        ensure_writeback_proposals_acceptable(data_store, project_id, [proposal])
    except WritebackPreValidationError as exc:
        raise unprocessable_from(exc) from exc
    return data_store.create_writeback_proposal(project_id, proposal)


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}",
    response_model=list[WritebackProposal],
    status_code=status.HTTP_201_CREATED,
)
def create_writeback_proposals_from_revision(
    project_id: str,
    revision_id: str,
    response: Response,
    force: bool = False,
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
    analysis: AnalysisService = Depends(get_analysis_service),
) -> list[WritebackProposal]:
    require_project(project_id, data_store)
    revision = data_store.get_manuscript_revision(project_id, revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        )

    snapshot = build_project_snapshot(project_id, data_store)

    def _generate() -> list[WritebackProposalCreate]:
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
        return [proposal for report in reports for proposal in report.writeback_proposals]

    outcome = analysis.run_writeback_generation(
        project_id=project_id,
        source_ref=f"manuscript_revision:{revision.id}",
        processor="local_writeback",
        fingerprint=writeback_input_fingerprint(
            revision,
            canon_entities=snapshot.canon_entities,
            memory_records=snapshot.memory_records,
        ),
        generate=_generate,
        force=force,
    )
    apply_analysis_headers(response, outcome)
    return outcome.proposals


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}/hermes",
    response_model=HermesRevisionProcessResponse,
    status_code=status.HTTP_201_CREATED,
)
def process_revision_with_hermes(
    project_id: str,
    revision_id: str,
    force: bool = False,
    data_store: WritingDataStore = Depends(get_data_store),
    analysis: AnalysisService = Depends(get_analysis_service),
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

    holder: dict = {}

    def _generate() -> list[WritebackProposalCreate]:
        result = HermesAgentClient().process_manuscript_revision(
            project_id=project_id,
            project_title=project_title,
            revision=revision,
            scene_contract=scene,
        )
        holder["result"] = result
        return result.writeback_proposals

    outcome = analysis.run_writeback_generation(
        project_id=project_id,
        source_ref=f"manuscript_revision:{revision.id}",
        processor="hermes",
        fingerprint=writeback_input_fingerprint(
            revision,
            extra={"processor": "hermes", "project_title": project_title},
        ),
        generate=_generate,
        force=force,
    )
    result = holder.get("result")
    response_model = HermesRevisionProcessResponse(
        status=result.status if result else "completed",
        summary=(
            result.summary
            if result
            else f"Replayed cached Hermes run {outcome.run.id} (v{outcome.run.run_version})."
        ),
        wiki_changes=result.wiki_changes if result else [],
        issues=result.issues if result else [],
        writeback_proposals=outcome.proposals,
        processed_source_ref=(
            result.processed_source_ref if result else f"manuscript_revision:{revision.id}"
        ),
        cached=outcome.cached,
        analysis_run_id=outcome.run.id,
    )
    return response_model


@router.post(
    "/projects/{project_id}/writeback/proposals/from-revision/{revision_id}/provider",
    response_model=list[WritebackProposal],
    status_code=status.HTTP_201_CREATED,
)
def create_provider_writeback_proposals_from_revision(
    project_id: str,
    revision_id: str,
    response: Response,
    force: bool = False,
    data_store: WritingDataStore = Depends(get_data_store),
    analysis: AnalysisService = Depends(get_analysis_service),
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

    canon_entities = data_store.list_canon_entities(project_id)
    memory_records = data_store.list_memory_records(project_id)

    def _generate() -> list[WritebackProposalCreate]:
        return build_provider_writeback_proposals(
            settings,
            revision,
            canon_entities,
            memory_records,
        )

    try:
        outcome = analysis.run_writeback_generation(
            project_id=project_id,
            source_ref=f"manuscript_revision:{revision.id}",
            processor="deepseek_writeback",
            fingerprint=writeback_input_fingerprint(
                revision,
                canon_entities=canon_entities,
                memory_records=memory_records,
                extra={"model": settings.model},
            ),
            generate=_generate,
            force=force,
        )
    except WritebackPreValidationError as exc:
        raise unprocessable_from(exc) from exc
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

    apply_analysis_headers(response, outcome)
    return outcome.proposals


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
    except ValidationError as exc:
        # A stored proposal whose payload no longer matches its target shape.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Write-back payload does not match the target record shape.",
        ) from exc
    except ValueError as exc:
        # Illegal review transitions and version conflicts share 409.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
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
