"""P2-01 application service for the Snowflake workflow.

Owns runtime-status reporting, artifact persistence with transactional
Wiki-index outbox enqueueing, and generation orchestration. Routers stay
pure HTTP: they parse requests, call this service, and map domain errors.
Since P1-03 this service only enqueues index jobs; executing them is the
job of the app-owned outbox dispatcher, which routes wake after enqueuing.
"""

from typing import Any
from math import ceil


from app.agents.writing_workflow import WritingWorkflow
from app.data.ports.snowflake import SnowflakeDataPort
from app.llm import (
    ModelGatewayError,
    ModelGatewayRegistry,
    ModelRuntime,
    default_model_gateway_registry,
    resolve_default_model_gateway,
)
from app.llm_wiki.interfaces import LlmWiki, WikiSourceDocument
from app.models import (
    SnowflakeArtifact,
    SnowflakeArtifactHead,
    SnowflakeArtifactRevision,
    SnowflakeArtifactRevisionCreate,
    SnowflakeArtifactRevisionPatch,
    SnowflakeGenerationCreate,
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeManuscriptProgress,
    SnowflakeRevisionDecisionRequest,
    SnowflakeRevisionDecisionResponse,
    SnowflakeRevisionPage,
    SnowflakeRecordDecisionRequest,
    SnowflakeRecordDecisionResponse,
    SnowflakeRecordPage,
    SnowflakeRecordRevision,
    SnowflakeRecordRevisionCreate,
    SnowflakeStep,
    SnowflakeStepState,
    SnowflakeValidationReport,
    WorkflowRuntimeStatus,
)
from app.outbox.events import snowflake_index_payload
from app.snowflake.step_spec import SNOWFLAKE_STEP_SPECS, get_step_spec
from app.snowflake.validators import (
    structured_payload_from_content,
    validate_scene_record_set_context,
    validate_snowflake_payload,
    validate_snowflake_record_generation,
    validate_snowflake_record_payload,
)


SNOWFLAKE_STEPS = [
    SnowflakeStep(
        number=spec.number,
        title=spec.title,
        artifact=spec.artifact_type,
        description=spec.description,
        dependencies=list(spec.dependencies),
        optional=spec.optional,
        schema_version=spec.schema_version,
        validator_name=spec.validator_name,
        virtual=spec.virtual,
    )
    for spec in SNOWFLAKE_STEP_SPECS
]


def merge_validation_reports(
    step_number: int,
    authoritative: SnowflakeValidationReport,
    workflow_report: SnowflakeValidationReport | None,
) -> SnowflakeValidationReport:
    """Preserve reviewer findings while de-duplicating service-side contract checks."""
    findings = list(authoritative.findings)
    seen = {(item.code, item.path, item.message, item.evidence) for item in findings}
    for item in workflow_report.findings if workflow_report else []:
        key = (item.code, item.path, item.message, item.evidence)
        if key not in seen:
            findings.append(item)
            seen.add(key)
    if any(item.severity == "critical" for item in findings):
        status = "failed"
    elif findings:
        status = "warnings"
    else:
        status = "passed"
    return SnowflakeValidationReport(
        step_number=step_number,
        status=status,
        findings=findings,
    )


class StepNotFoundError(LookupError):
    pass


class ArtifactNotFoundError(LookupError):
    pass


class RevisionNotFoundError(LookupError):
    pass


class SnowflakeRecordValidationError(ValueError):
    def __init__(self, message: str, report=None):
        self.report = report
        super().__init__(message)


class SnowflakeService:
    def __init__(
        self,
        data_store: SnowflakeDataPort,
        llm_wiki: LlmWiki,
        registry: ModelGatewayRegistry | None = None,
    ):
        self.data_store = data_store
        self.llm_wiki = llm_wiki
        self.registry = registry if registry is not None else default_model_gateway_registry

    # -- steps -----------------------------------------------------------

    @staticmethod
    def list_steps() -> list[SnowflakeStep]:
        return SNOWFLAKE_STEPS

    @staticmethod
    def get_step(step_number: int) -> SnowflakeStep:
        for step in SNOWFLAKE_STEPS:
            if step.number == step_number:
                return step
        raise StepNotFoundError(f"Snowflake step {step_number} not found.")

    # -- provider status --------------------------------------------------

    def runtime_status(self) -> WorkflowRuntimeStatus:
        """Report the configured generation backend without raising."""
        try:
            gateway, _skip_reason = resolve_default_model_gateway(self.registry)
        except ModelGatewayError as exc:
            return WorkflowRuntimeStatus(
                runtime="local_deterministic",
                runtime_kind="local_deterministic",
                provider="local",
                provider_configured=False,
                details=f"{exc.safe_message} Using deterministic local drafts.",
            )
        described = gateway.describe()
        return WorkflowRuntimeStatus(
            runtime=f"provider_{described.provider_id}",
            runtime_kind="model_gateway",
            provider=described.provider_id,
            provider_configured=True,
            model=described.model_id,
            base_url=described.base_url,
            details=f"{described.provider_id} model gateway is configured for draft generation.",
        )

    # -- artifacts ---------------------------------------------------------

    def list_artifacts(self, project_id: str) -> list[SnowflakeArtifact]:
        return self.data_store.list_snowflake_artifacts(project_id)

    def get_artifact(self, project_id: str, step_number: int) -> SnowflakeArtifact:
        self.get_step(step_number)
        artifact = self.data_store.get_snowflake_artifact(project_id, step_number)
        if artifact is None:
            raise ArtifactNotFoundError("Snowflake artifact not found.")
        return artifact

    def list_step_states(self, project_id: str) -> list[SnowflakeStepState]:
        heads = {
            head.step_number: head for head in self.data_store.list_snowflake_heads(project_id)
        }
        pending = self.data_store.snowflake_pending_counts(project_id)
        result: list[SnowflakeStepState] = []
        for step in SNOWFLAKE_STEPS:
            head = heads.get(step.number) or SnowflakeArtifactHead(
                project_id=project_id, step_number=step.number
            )
            accepted = (
                self.data_store.get_snowflake_revision(project_id, head.accepted_revision_id)
                if head.accepted_revision_id
                else None
            )
            state = head.state
            stale_reason = head.stale_reason
            if (
                step.number in {6, 7, 8, 9}
                and accepted is not None
                and not self.data_store.list_accepted_snowflake_records(project_id, step.number)
            ):
                state = "stale"
                stale_reason = (
                    "Legacy Artifact is preserved for reference, but this step requires "
                    "accepted structured records before it is authoritative."
                )
            result.append(
                SnowflakeStepState(
                    step=step,
                    state=state,
                    accepted_revision=accepted,
                    pending_count=pending.get(step.number, 0),
                    stale_reason=stale_reason,
                    stale_trigger_revision_id=head.stale_trigger_revision_id,
                )
            )
        return result

    def list_revisions(
        self, project_id: str, step_number: int, *, page: int, page_size: int
    ) -> SnowflakeRevisionPage:
        self.get_step(step_number)
        revisions, total = self.data_store.list_snowflake_revisions(
            project_id,
            step_number,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return SnowflakeRevisionPage(
            data=revisions,
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def create_revision(
        self, project_id: str, create: SnowflakeArtifactRevisionCreate
    ) -> SnowflakeArtifactRevision:
        spec = get_step_spec(create.step_number)
        if spec.virtual:
            raise ValueError("Snowflake step 10 is a virtual Manuscript milestone.")
        if create.schema_version != spec.schema_version:
            raise ValueError(
                f"Step {create.step_number} requires schema version {spec.schema_version}."
            )
        normalized = create
        if not create.structured_payload:
            parsed = structured_payload_from_content(create.content)
            if parsed:
                normalized = create.model_copy(update={"structured_payload": parsed})
        return self.data_store.create_snowflake_revision(project_id, normalized)

    def patch_revision(
        self,
        project_id: str,
        revision_id: str,
        patch: SnowflakeArtifactRevisionPatch,
    ) -> SnowflakeArtifactRevision:
        revision = self.data_store.patch_snowflake_revision(
            project_id,
            revision_id,
            content=patch.content,
            structured_payload=patch.structured_payload,
        )
        if revision is None:
            raise RevisionNotFoundError("Snowflake revision not found.")
        return revision

    def decide_revision(
        self,
        project_id: str,
        revision_id: str,
        request: SnowflakeRevisionDecisionRequest,
    ) -> SnowflakeRevisionDecisionResponse:
        revision, head, affected, job_id = self.data_store.decide_snowflake_revision(
            project_id=project_id,
            revision_id=revision_id,
            decision=request.decision,
            expected_head_revision_id=request.expected_head_revision_id,
            review_reason=request.review_reason,
        )
        validation = validate_snowflake_payload(
            revision.step_number, revision.content, revision.structured_payload
        )
        return SnowflakeRevisionDecisionResponse(
            revision=revision,
            head=head,
            affected_steps=affected,
            outbox_job_id=job_id,
            validation_report=validation,
        )

    def skip_step(self, project_id: str, step_number: int) -> SnowflakeArtifactHead:
        self.get_step(step_number)
        return self.data_store.skip_snowflake_step(project_id, step_number)

    def list_records(
        self, project_id: str, step_number: int, *, page: int, page_size: int
    ) -> SnowflakeRecordPage:
        if step_number not in {6, 7, 8, 9}:
            raise ValueError("Record storage is available only for Snowflake steps 6–9.")
        records, total = self.data_store.list_snowflake_records(
            project_id, step_number, limit=page_size, offset=(page - 1) * page_size
        )
        return SnowflakeRecordPage(
            data=records,
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def create_record_revision(
        self, project_id: str, create: SnowflakeRecordRevisionCreate
    ) -> SnowflakeRecordRevision:
        validation = validate_snowflake_record_payload(create.step_number, create.payload)
        if validation.status == "failed":
            raise SnowflakeRecordValidationError(
                f"Step {create.step_number} record does not match its structured contract.",
                validation,
            )
        return self.data_store.create_snowflake_record_revision(project_id, create)

    def list_record_revisions(
        self,
        project_id: str,
        step_number: int,
        record_id: str,
        *,
        page: int,
        page_size: int,
    ) -> SnowflakeRecordPage:
        if step_number not in {6, 7, 8, 9}:
            raise ValueError("Record storage is available only for Snowflake steps 6–9.")
        revisions, total = self.data_store.list_snowflake_record_revisions(
            project_id,
            step_number,
            record_id,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return SnowflakeRecordPage(
            data=revisions,
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    def decide_record_revision(
        self,
        project_id: str,
        revision_id: str,
        request: SnowflakeRecordDecisionRequest,
    ) -> SnowflakeRecordDecisionResponse:
        revision = self.data_store.get_snowflake_record_revision(project_id, revision_id)
        if revision is None:
            raise LookupError("Snowflake record revision not found.")
        if request.decision == "accepted":
            validation = validate_snowflake_record_payload(revision.step_number, revision.payload)
            if validation.status == "failed":
                raise SnowflakeRecordValidationError(
                    "Snowflake record revision has blocking validation findings.",
                    validation,
                )
            self._validate_contextual_record_acceptance(project_id, revision)
        return self.data_store.decide_snowflake_record_revision(
            project_id,
            revision_id,
            decision=request.decision,
            expected_revision_id=request.expected_revision_id,
            review_reason=request.review_reason,
        )

    def _validate_contextual_record_acceptance(
        self,
        project_id: str,
        candidate: SnowflakeRecordRevision,
    ) -> None:
        """Validate references and set-level invariants before changing a record head."""
        if candidate.step_number != 8:
            return
        accepted = self.data_store.list_accepted_snowflake_records(project_id, 8)
        record_set = [record for record in accepted if record.record_id != candidate.record_id]
        record_set.append(candidate)
        report = validate_scene_record_set_context(
            record_set,
            self.data_store.list_canon_entities(project_id),
            self.data_store.list_story_threads(project_id),
        )
        if report.status != "failed":
            return
        raise SnowflakeRecordValidationError(
            "Snowflake record revision has blocking contextual findings.",
            report,
        )

    def manuscript_progress(self, project_id: str) -> SnowflakeManuscriptProgress:
        scenes = self.data_store.list_scene_contracts(project_id)
        proposals = self.data_store.list_manuscript_proposals(project_id)
        revisions = self.data_store.list_manuscript_revisions(project_id)
        accepted_scene_ids = {revision.scene_id for revision in revisions}
        pending = sum(1 for proposal in proposals if proposal.status == "pending_review")
        heads = {
            head.step_number: head for head in self.data_store.list_snowflake_heads(project_id)
        }
        plan_stale = any(
            heads.get(step) is not None and heads[step].state == "stale" for step in (8, 9)
        )
        stale_count = (
            len(scenes)
            if plan_stale
            else sum(
                1
                for scene in scenes
                if scene.id in accepted_scene_ids
                and scene.manuscript_plan_version < scene.plan_version
            )
        )
        accepted_count = sum(1 for scene in scenes if scene.id in accepted_scene_ids)
        total = len(scenes)
        percent = round((accepted_count / total) * 100) if total else 0
        return SnowflakeManuscriptProgress(
            project_id=project_id,
            total_scene_contracts=total,
            pending_manuscript_proposals=pending,
            accepted_latest_revisions=accepted_count,
            stale_scene_count=stale_count,
            completion_percent=percent,
            complete=bool(total) and accepted_count == total and not stale_count,
        )

    def save_artifact(
        self, project_id: str, step_number: int, content: str
    ) -> tuple[SnowflakeArtifact, str | None]:
        """Compatibility save: append a human draft without committing a head."""
        step = self.get_step(step_number)
        if step.virtual:
            raise ValueError("Snowflake step 10 is a virtual Manuscript milestone.")
        revision = self.create_revision(
            project_id,
            SnowflakeArtifactRevisionCreate(
                step_number=step_number,
                content=content,
                source="human",
                schema_version=step.schema_version,
            ),
        )
        artifact = SnowflakeArtifact(
            project_id=revision.project_id,
            step_number=step_number,
            artifact=step.artifact,
            content=revision.content,
        )
        return artifact, None

    def generate(
        self, request: SnowflakeGenerationRequest, workflow: WritingWorkflow
    ) -> tuple[SnowflakeGenerationResponse, str | None]:
        """Compatibility generation: create a pending revision, never a committed head."""
        step = self.get_step(request.step_number)
        if step.virtual:
            raise ValueError("Snowflake step 10 is a virtual Manuscript milestone.")
        if request.step_number in {6, 7, 8, 9}:
            target_records = self.data_store.get_snowflake_records(
                request.project_id, request.step_number, request.target_record_ids
            )
            if len(target_records) != len(request.target_record_ids):
                raise ValueError("One or more target Snowflake records have no accepted revision.")
            record_request = request.model_copy(
                update={
                    "target_records": [
                        {
                            "record_id": record.record_id,
                            "revision_id": record.id,
                            "position": record.position,
                            "payload": record.payload,
                        }
                        for record in target_records
                    ]
                }
            )
            return self._generate_record_revisions(record_request, workflow), None
        generated = workflow.run_snowflake_generation(request)
        spec = get_step_spec(request.step_number)
        if generated.step_number != request.step_number or generated.artifact != spec.artifact_type:
            raise ValueError("Provider returned a Snowflake artifact for the wrong step or type.")
        structured_payload = structured_payload_from_content(generated.content)
        revision = self.data_store.create_snowflake_revision(
            request.project_id,
            SnowflakeArtifactRevisionCreate(
                step_number=request.step_number,
                content=generated.content,
                structured_payload=structured_payload,
                source="ai",
                schema_version=spec.schema_version,
            ),
            status="pending_review",
            source="ai",
        )
        validation = validate_snowflake_payload(
            request.step_number, generated.content, structured_payload
        )
        validation = merge_validation_reports(
            request.step_number, validation, generated.validation_report
        )
        return generated.model_copy(
            update={"revision": revision, "validation_report": validation}
        ), None

    def generate_revision(
        self,
        project_id: str,
        request: SnowflakeGenerationCreate,
        workflow: WritingWorkflow,
    ) -> SnowflakeGenerationResponse:
        target_records: list[dict[str, Any]] = []
        if request.target_record_ids and request.step_number in {6, 7, 8, 9}:
            records = self.data_store.get_snowflake_records(
                project_id, request.step_number, request.target_record_ids
            )
            target_records = [
                {
                    "record_id": record.record_id,
                    "revision_id": record.id,
                    "position": record.position,
                    "payload": record.payload,
                }
                for record in records
            ]
            if len(target_records) != len(request.target_record_ids):
                raise ValueError("One or more target Snowflake records have no accepted revision.")
        generation_request = SnowflakeGenerationRequest(
            project_id=project_id,
            step_number=request.step_number,
            user_input=request.instruction,
            base_revision_id=request.base_revision_id,
            target_record_ids=request.target_record_ids,
            target_records=target_records,
            generation_mode=request.generation_mode,
            previous_artifacts_context_chars=request.previous_artifacts_context_chars,
            model_profile=request.model_profile,
            allow_fallback=request.allow_fallback,
            allow_repair=request.allow_repair,
        )
        if request.step_number not in {6, 7, 8, 9}:
            return self.generate(generation_request, workflow)[0]

        return self._generate_record_revisions(generation_request, workflow)

    def _generate_record_revisions(
        self,
        request: SnowflakeGenerationRequest,
        workflow: WritingWorkflow,
    ) -> SnowflakeGenerationResponse:
        """Generate Step 6-9 record proposals without creating a blob revision."""
        generated = workflow.run_snowflake_generation(request)
        spec = get_step_spec(request.step_number)
        if generated.step_number != request.step_number or generated.artifact != spec.artifact_type:
            raise ValueError("Provider returned a Snowflake artifact for the wrong step or type.")
        expected_ids = request.target_record_ids if request.target_record_ids else None
        generated_records, validation = validate_snowflake_record_generation(
            request.step_number,
            generated.content,
            expected_ids,
        )
        if validation.status == "failed":
            raise SnowflakeRecordValidationError(
                "Provider returned invalid Snowflake records.",
                validation,
            )
        validation = merge_validation_reports(
            request.step_number, validation, generated.validation_report
        )

        accepted_records = self.data_store.get_snowflake_records(
            request.project_id,
            request.step_number,
            [record.record_id for record in generated_records],
        )
        accepted_by_id = {record.record_id: record for record in accepted_records}
        target_positions = {
            record["record_id"]: int(record["position"]) for record in request.target_records
        }
        creates = []
        for index, record in enumerate(generated_records, start=1):
            accepted = accepted_by_id.get(record.record_id)
            raw_sequence = record.payload.get("sequence")
            inferred_position = raw_sequence if isinstance(raw_sequence, int) else index
            creates.append(
                SnowflakeRecordRevisionCreate(
                    step_number=request.step_number,
                    record_id=record.record_id,
                    position=target_positions.get(
                        record.record_id,
                        accepted.position if accepted else inferred_position,
                    ),
                    payload=record.payload,
                    base_revision_id=accepted.id if accepted else "",
                    source="ai",
                )
            )
        record_revisions = self.data_store.create_snowflake_record_revisions(
            request.project_id,
            creates,
            status="pending_review",
        )
        return generated.model_copy(
            update={
                "revision": None,
                "record_revisions": record_revisions,
                "validation_report": validation,
            }
        )


# ---------------------------------------------------------------------------
# Workflow selection shared by application callers
# ---------------------------------------------------------------------------


class SelectableWritingWorkflow:
    def __init__(
        self,
        *,
        local: WritingWorkflow,
        remote: WritingWorkflow,
        runtime: ModelRuntime,
    ) -> None:
        self.local = local
        self.remote = remote
        self.runtime = runtime

    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        if request.model_profile or self.runtime.has_configured_gateway():
            return self.remote.run_snowflake_generation(request)
        return self.local.run_snowflake_generation(request)


def snowflake_wiki_document(artifact: SnowflakeArtifact) -> WikiSourceDocument:
    """Kept for compatibility; the mapping now lives in app.outbox.events."""
    return WikiSourceDocument.model_validate(snowflake_index_payload(artifact))
