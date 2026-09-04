from difflib import unified_diff
from fastapi import Depends, HTTPException, status

from app.agents.manuscript_workflow import generate_manuscript_scene
from app.analysis.consistency import CONSISTENCY_PROCESSOR, check_revision
from app.analysis.models import ConsistencyReport, ConsistencyReportSummary
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.narrative import NarrativeSnapshot
from app.data import WritingDataStore, get_data_store, utc_now
from app.llm import (
    ModelGatewayError,
    ModelGatewayRegistry,
    ModelRuntime,
    default_model_gateway_registry,
)
from app.manuscript_export import build_export_markdown
from app.models import (
    LegacyManuscriptImportCreate,
    ManuscriptExportResponse,
    ManuscriptProposal,
    ManuscriptProposalAcceptance,
    ManuscriptProposalCreate,
    ManuscriptRevisionDiff,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
    ModelExecutionOptions,
)
from app.review.service import conflict_from, decide
from app.services.compile_service import build_compile_checklist, build_scene_draft


class ManuscriptService:
    def __init__(
        self,
        data_store: WritingDataStore = Depends(get_data_store),
        cognition: CognitionRegistry = Depends(get_cognition_registry),
    ):
        self.data_store = data_store
        self.cognition = cognition
        # Constructor params double as FastAPI DI defaults, so provider
        # resolution stays a plain attribute instead of an injected argument.
        self.gateway_registry: ModelGatewayRegistry = default_model_gateway_registry

    def update_scene(
        self, project_id: str, scene_id: str, update: ManuscriptSceneUpdate
    ) -> ManuscriptScene:
        try:
            scene = self.data_store.update_manuscript_scene(project_id, scene_id, update)
        except ValueError as exc:
            raise conflict_from(exc) from exc
        if scene is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Accepted manuscript scene not found."
            )
        return scene

    def import_legacy_snowflake_draft(
        self,
        project_id: str,
        revision_id: str,
        selection: LegacyManuscriptImportCreate,
    ) -> ManuscriptProposal:
        revision = self.data_store.get_snowflake_revision(project_id, revision_id)
        if revision is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Legacy Snowflake draft not found.",
            )
        if revision.step_number != 10 or revision.status != "legacy_draft":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only preserved Step 10 legacy drafts can be imported.",
            )
        if self.data_store.get_scene_contract(project_id, selection.scene_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scene contract not found.",
            )
        if selection.content not in revision.content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Imported content must be an exact selection from the legacy draft.",
            )
        return self.data_store.create_manuscript_proposal(
            project_id,
            ManuscriptProposalCreate(
                scene_id=selection.scene_id,
                source="legacy_snowflake_import",
                title=selection.title,
                content=selection.content,
                context=f"Human selection from preserved Snowflake revision {revision.id}.",
                checklist=[
                    "Selection boundaries were chosen by a human.",
                    "Review Canon and scene consistency before accepting.",
                    "Import remains a proposal until explicit acceptance.",
                ],
            ),
        )

    def export(self, project_id: str) -> ManuscriptExportResponse:
        project = self.data_store.get_project(project_id)
        scenes = self.data_store.list_manuscript_scenes(project_id)
        scene_contracts = {s.id: s for s in self.data_store.list_scene_contracts(project_id)}
        chapters = self.data_store.list_manuscript_chapters(project_id)
        chapter_order = {c.id: c.sequence for c in chapters}
        ordered_scene_pairs = sorted(
            [(s, scene_contracts.get(s.scene_id)) for s in scenes],
            key=lambda p: (
                chapter_order.get(p[1].chapter_id, 9999) if p[1] else 9999,
                p[1].sequence if p[1] else 9999,
                p[0].title,
            ),
        )
        title = project.title if project else project_id
        content = build_export_markdown(title, chapters, ordered_scene_pairs)
        return ManuscriptExportResponse(
            project_id=project_id,
            title=title,
            scene_count=len(ordered_scene_pairs),
            content=content,
            generated_at=utc_now(),
        )

    def diff_revisions(
        self, project_id: str, left_id: str, right_id: str
    ) -> ManuscriptRevisionDiff:
        left = self.data_store.get_manuscript_revision(project_id, left_id)
        right = self.data_store.get_manuscript_revision(project_id, right_id)
        if not left or not right:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript revision not found."
            )
        return ManuscriptRevisionDiff(
            project_id=project_id,
            left_revision_id=left.id,
            right_revision_id=right.id,
            left_title=f"{left.title} v{left.version}",
            right_title=f"{right.title} v{right.version}",
            diff_lines=list(
                unified_diff(
                    left.content.splitlines(),
                    right.content.splitlines(),
                    fromfile=f"{left.title} v{left.version}",
                    tofile=f"{right.title} v{right.version}",
                    lineterm="",
                )
            ),
        )

    def restore_revision(self, project_id: str, revision_id: str) -> ManuscriptScene:
        scene = self.data_store.restore_manuscript_revision(project_id, revision_id)
        if not scene:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript revision not found."
            )
        return scene

    def generate_local_proposal(self, project_id: str, scene_id: str) -> ManuscriptProposal:
        scene, project = self._get_scene_and_project(project_id, scene_id)
        context = self._build_context(project_id, project, scene)
        proposal = ManuscriptProposalCreate(
            scene_id=scene.id,
            title=f"{scene.sequence}. {scene.title}",
            content=build_scene_draft(scene),
            context=context,
            checklist=build_compile_checklist(),
        )
        return self.data_store.create_manuscript_proposal(project_id, proposal)

    def generate_provider_proposal(
        self,
        project_id: str,
        scene_id: str,
        options: ModelExecutionOptions | None = None,
    ) -> ManuscriptProposal:
        scene, project = self._get_scene_and_project(project_id, scene_id)
        snapshot = self._build_snapshot(project_id, project, scene)
        context = snapshot.render_generation_context()
        try:
            execution = generate_manuscript_scene(
                ModelRuntime(self.gateway_registry, recorder=self.data_store),
                context,
                project_id,
                options,
            )
        except ModelGatewayError as exc:
            raise HTTPException(
                status_code=(
                    status.HTTP_501_NOT_IMPLEMENTED
                    if exc.is_configuration_error
                    else status.HTTP_502_BAD_GATEWAY
                ),
                detail=exc.safe_message,
            ) from exc

        draft = execution.validated_value
        proposal = ManuscriptProposalCreate(
            scene_id=scene.id,
            title=f"{scene.sequence}. {scene.title} provider draft",
            content=draft.manuscript_prose,
            context=context,
            checklist=[
                *build_compile_checklist(),
                "Provider draft is reviewed before accepting.",
                f"Review {len(draft.new_fact_candidates)} new fact candidate(s).",
                f"Review {len(draft.design_deviation_proposals)} design deviation proposal(s).",
                f"Resolve {len(draft.continuity_questions)} continuity question(s).",
            ],
        )
        return self.data_store.create_manuscript_proposal(project_id, proposal)

    def update_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        status_str: str,
        draft: ManuscriptProposalAcceptance | None = None,
    ) -> ManuscriptProposal:
        current = self.data_store.get_manuscript_proposal(project_id, proposal_id)
        if not current:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript proposal not found."
            )
        if current.status == status_str:
            return current
        try:
            decide(current.status, status_str, "Manuscript proposal")
        except ValueError as exc:
            raise conflict_from(exc) from exc
        if status_str == "accepted":
            if draft is None:
                scene = self.data_store.get_manuscript_scene(project_id, current.scene_id)
                draft = ManuscriptProposalAcceptance(
                    title=current.title,
                    content=current.content,
                    expected_scene_version=scene.version if scene else 0,
                )
            report = self.preview_proposal_consistency(project_id, proposal_id, draft)
            if report.summary.critical_count:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": "Critical consistency findings must be resolved before acceptance.",
                        "consistency_report": report.model_dump(),
                    },
                )
            try:
                scene = self.data_store.accept_manuscript_proposal(
                    project_id, proposal_id, draft=draft
                )
            except ValueError as exc:
                raise conflict_from(exc) from exc
            proposal = self.data_store.get_manuscript_proposal(project_id, proposal_id)
            if not scene or not proposal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript proposal not found."
                )
            return proposal
        try:
            proposal = self.data_store.update_manuscript_proposal_status(
                project_id, proposal_id, status_str
            )
        except ValueError as exc:
            # Lost a transition race between the read and the write.
            raise conflict_from(exc) from exc
        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript proposal not found."
            )
        return proposal

    def preview_proposal_consistency(
        self,
        project_id: str,
        proposal_id: str,
        draft: ManuscriptProposalAcceptance,
    ) -> ConsistencyReport:
        proposal = self.data_store.get_manuscript_proposal(project_id, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Manuscript proposal not found."
            )
        snapshot = NarrativeSnapshot.for_scene(
            project_id=project_id,
            scene_id=proposal.scene_id,
            data_store=self.data_store,
            # Acceptance correctness is based on authoritative scene/canon data.
            # Advisory cognition outages must not make manuscript review unavailable.
            cognition=None,
        )
        candidate = ManuscriptRevision(
            id=f"proposal-preview:{proposal.id}",
            project_id=project_id,
            scene_id=proposal.scene_id,
            proposal_id=proposal.id,
            title=draft.title,
            content=draft.content,
            version=draft.expected_scene_version + 1,
            created_at=utc_now(),
        )
        findings = check_revision(
            candidate, snapshot.scene, snapshot.canon_entities, snapshot.world_truth
        )
        return ConsistencyReport(
            project_id=project_id,
            source_ref=f"manuscript_proposal:{proposal.id}",
            processor=CONSISTENCY_PROCESSOR,
            summary=ConsistencyReportSummary(
                finding_count=len(findings),
                critical_count=sum(item.severity == "critical" for item in findings),
                warning_count=sum(item.severity == "warning" for item in findings),
                info_count=sum(item.severity == "info" for item in findings),
            ),
            findings=findings,
        )

    def _get_scene_and_project(self, project_id: str, scene_id: str):
        scene = self.data_store.get_scene_contract(project_id, scene_id)
        if not scene:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Scene contract not found."
            )
        project = self.data_store.get_project(project_id)
        return scene, project

    def _build_snapshot(self, project_id: str, project, scene) -> NarrativeSnapshot:
        resolved_project_id = project.id if project else project_id
        return NarrativeSnapshot.for_scene(
            project_id=resolved_project_id,
            scene_id=scene.id,
            data_store=self.data_store,
            cognition=self.cognition,
        )

    def _build_context(self, project_id: str, project, scene) -> str:
        return self._build_snapshot(project_id, project, scene).render_generation_context()
