"""Consistency report endpoints (P1-06).

Runs or replays the deterministic consistency checker for one accepted
manuscript revision. Findings are advisory evidence for the author; this
router never mutates manuscript or Canon state.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError

from app.analysis.consistency import (
    CONSISTENCY_PROCESSOR,
    build_consistency_fingerprint,
    check_revision,
)
from app.analysis.http import apply_analysis_headers, get_analysis_service
from app.analysis.models import (
    ConsistencyFinding,
    ConsistencyReport,
    ConsistencyReportSummary,
    StyleDriftReport,
    StyleProfile,
)
from app.analysis.style import build_style_drift_report, build_style_profile
from app.analysis.service import AnalysisService
from app.cognition.snapshots import NarrativeSnapshot
from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project


router = APIRouter(tags=["analysis"])


def _accepted_style_texts(project_id: str, data_store: WritingDataStore, pov: str = "") -> list[str]:
    contracts = {item.id: item for item in data_store.list_scene_contracts(project_id)}
    normalized_pov = pov.strip().lower()
    texts = []
    for manuscript_scene in data_store.list_manuscript_scenes(project_id):
        contract = contracts.get(manuscript_scene.scene_id)
        if normalized_pov and (contract is None or contract.pov.strip().lower() != normalized_pov):
            continue
        texts.append(manuscript_scene.content)
    return texts


def _report_from_run(
    project_id: str,
    source_ref: str,
    run,
    findings: list[ConsistencyFinding],
) -> ConsistencyReport:
    summary = ConsistencyReportSummary(
        finding_count=len(findings),
        critical_count=sum(1 for item in findings if item.severity == "critical"),
        warning_count=sum(1 for item in findings if item.severity == "warning"),
        info_count=sum(1 for item in findings if item.severity == "info"),
    )
    return ConsistencyReport(
        project_id=project_id,
        source_ref=source_ref,
        processor=CONSISTENCY_PROCESSOR,
        run_id=run.id,
        run_version=run.run_version,
        summary=summary,
        findings=findings,
    )


def _load_revision(project_id: str, revision_id: str, data_store: WritingDataStore):
    revision = data_store.get_manuscript_revision(project_id, revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manuscript revision not found.",
        )
    return revision


@router.post(
    "/projects/{project_id}/analysis/consistency/from-revision/{revision_id}",
    response_model=ConsistencyReport,
)
def run_consistency_report(
    project_id: str,
    revision_id: str,
    response: Response,
    force: bool = False,
    data_store: WritingDataStore = Depends(get_data_store),
    analysis: AnalysisService = Depends(get_analysis_service),
) -> ConsistencyReport:
    require_project(project_id, data_store)
    revision = _load_revision(project_id, revision_id, data_store)
    snapshot = NarrativeSnapshot.for_scene(
        project_id=project_id,
        scene_id=revision.scene_id,
        data_store=data_store,
    )
    source_ref = f"manuscript_revision:{revision.id}"

    outcome = analysis.run_consistency_analysis(
        project_id=project_id,
        source_ref=source_ref,
        fingerprint=build_consistency_fingerprint(
            revision,
            snapshot.scene,
            snapshot.canon_entities,
            snapshot.world_truth,
        ),
        check=lambda: check_revision(
            revision,
            snapshot.scene,
            snapshot.canon_entities,
            snapshot.world_truth,
        ),
        force=force,
    )
    apply_analysis_headers(response, outcome)
    report = _report_from_run(project_id, source_ref, outcome.run, outcome.findings)
    report.cached = outcome.cached
    return report


@router.get(
    "/projects/{project_id}/analysis/style/profile",
    response_model=StyleProfile,
)
def get_style_profile(
    project_id: str,
    pov: str = "",
    data_store: WritingDataStore = Depends(get_data_store),
) -> StyleProfile:
    require_project(project_id, data_store)
    scope = f"pov:{pov.strip()}" if pov.strip() else "project"
    return build_style_profile(
        project_id,
        _accepted_style_texts(project_id, data_store, pov),
        scope=scope,
    )


@router.get(
    "/projects/{project_id}/analysis/style/drift/from-revision/{revision_id}",
    response_model=StyleDriftReport,
)
def get_style_drift_report(
    project_id: str,
    revision_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> StyleDriftReport:
    require_project(project_id, data_store)
    revision = _load_revision(project_id, revision_id, data_store)
    target_scene = data_store.get_scene_contract(project_id, revision.scene_id)
    contracts = {item.id: item for item in data_store.list_scene_contracts(project_id)}
    target_sequence = target_scene.sequence if target_scene else 9999
    target_pov = target_scene.pov.strip() if target_scene else ""

    earlier = []
    earlier_same_pov = []
    for manuscript_scene in data_store.list_manuscript_scenes(project_id):
        contract = contracts.get(manuscript_scene.scene_id)
        if contract is None or contract.sequence >= target_sequence:
            continue
        earlier.append(manuscript_scene.content)
        if target_pov and contract.pov.strip().lower() == target_pov.lower():
            earlier_same_pov.append(manuscript_scene.content)
    profile_texts = earlier_same_pov or earlier
    scope = f"pov:{target_pov}" if earlier_same_pov and target_pov else "project:earlier-scenes"
    profile = build_style_profile(project_id, profile_texts, scope=scope)
    return build_style_drift_report(
        project_id=project_id,
        source_ref=f"manuscript_revision:{revision.id}",
        profile=profile,
        text=revision.content,
    )


@router.get(
    "/projects/{project_id}/analysis/consistency/from-revision/{revision_id}",
    response_model=ConsistencyReport,
)
def get_latest_consistency_report(
    project_id: str,
    revision_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    analysis: AnalysisService = Depends(get_analysis_service),
) -> ConsistencyReport:
    require_project(project_id, data_store)
    revision = _load_revision(project_id, revision_id, data_store)
    source_ref = f"manuscript_revision:{revision.id}"
    run = analysis.latest_consistency_run(project_id, source_ref)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No consistency report has been generated for this revision.",
        )
    try:
        findings = [
            ConsistencyFinding.model_validate(item) for item in run.result_json.get("findings", [])
        ]
    except (ValidationError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The stored consistency report no longer parses; re-run the check to regenerate it."
            ),
        )
    report = _report_from_run(project_id, source_ref, run, findings)
    report.cached = True
    return report
