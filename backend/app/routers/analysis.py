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
)
from app.analysis.service import AnalysisService
from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project


router = APIRouter(tags=["analysis"])


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
    scene = data_store.get_scene_contract(project_id, revision.scene_id)
    canon_entities = data_store.list_canon_entities(project_id)
    source_ref = f"manuscript_revision:{revision.id}"

    outcome = analysis.run_consistency_analysis(
        project_id=project_id,
        source_ref=source_ref,
        fingerprint=build_consistency_fingerprint(revision, scene, canon_entities),
        check=lambda: check_revision(revision, scene, canon_entities),
        force=force,
    )
    apply_analysis_headers(response, outcome)
    report = _report_from_run(project_id, source_ref, outcome.run, outcome.findings)
    report.cached = outcome.cached
    return report


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
