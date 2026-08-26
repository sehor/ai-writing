"""P2-01 application service for Canon / Memory write-back proposals.

Owns proposal review helpers plus the three generation paths:
deterministic local extraction, the external Hermes agent port, and
provider-backed suggestions through the P2-02 registry. Routers stay
pure HTTP and map domain errors onto status codes.
"""

from fastapi import Depends
from pydantic import ValidationError

from app.agents.writing_workflow import WorkflowNotConfiguredError
from app.analysis.http import get_analysis_service
from app.analysis.service import AnalysisService, writeback_input_fingerprint
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store
from app.integrations.hermes import HermesAgentClient
from app.integrations.provider_registry import (
    LocalDeterministicProvider,
    ProviderDependencies,
    ProviderExecutionError,
    ProviderRegistry,
    ProviderUnavailableError,
    default_provider_registry,
)
from app.observability import timed_operation
from app.models import (
    HermesRevisionProcessResponse,
    WritebackProposal,
    WritebackProposalCreate,
)
from app.review.service import (
    WritebackPreValidationError,
    ensure_writeback_proposals_acceptable,
)


class RevisionNotFoundError(LookupError):
    pass


class SceneForRevisionNotFoundError(LookupError):
    pass


class WritebackService:
    def __init__(
        self,
        data_store: WritingDataStore,
        cognition: CognitionRegistry,
        analysis: AnalysisService,
        registry: ProviderRegistry | None = None,
    ):
        self.data_store = data_store
        self.cognition = cognition
        self.analysis = analysis
        self.registry = registry if registry is not None else default_provider_registry

    # -- review ---------------------------------------------------------------

    def list_proposals(self, project_id: str) -> list[WritebackProposal]:
        return self.data_store.list_writeback_proposals(project_id)

    def create_proposal(
        self, project_id: str, proposal: WritebackProposalCreate
    ) -> WritebackProposal:
        """Validate against current data before insert (P1-03 contract)."""
        ensure_writeback_proposals_acceptable(self.data_store, project_id, [proposal])
        return self.data_store.create_writeback_proposal(project_id, proposal)

    def update_status(
        self, project_id: str, proposal_id: str, status_str: str
    ) -> WritebackProposal | None:
        """Returns None when the proposal does not exist.

        Raises ValidationError for payload/record shape mismatches (422),
        ValueError for illegal transitions and version conflicts (409), and
        sqlite3.IntegrityError for duplicate accepted records (409).
        """
        return self.data_store.update_writeback_proposal_status(
            project_id,
            proposal_id,
            status_str,
        )

    # -- generation ------------------------------------------------------------

    def generate_from_revision(self, project_id: str, revision_id: str, force: bool = False):
        """Deterministic local suggestions extracted from one revision."""
        revision = self._require_revision(project_id, revision_id)
        snapshot = build_project_snapshot(project_id, self.data_store)
        provider = LocalDeterministicProvider(cognition=self.cognition)

        def _generate() -> list[WritebackProposalCreate]:
            with timed_operation(
                "provider_call",
                operation="generate_writebacks",
                provider=str(getattr(provider, "name", "unknown")),
                project_id=project_id,
            ):
                return provider.generate_writebacks(revision, snapshot)

        return self.analysis.run_writeback_generation(
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

    def process_with_hermes(
        self, project_id: str, revision_id: str, force: bool = False
    ) -> HermesRevisionProcessResponse:
        """Send the revision delta through the external Hermes agent port."""
        revision = self._require_revision(project_id, revision_id)
        scene = self.data_store.get_scene_contract(project_id, revision.scene_id)
        if scene is None:
            raise SceneForRevisionNotFoundError("Scene contract not found for manuscript revision.")
        project = self.data_store.get_project(project_id)
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

        outcome = self.analysis.run_writeback_generation(
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
        return HermesRevisionProcessResponse(
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

    def generate_provider_from_revision(
        self, project_id: str, revision_id: str, force: bool = False
    ):
        """Structured write-back suggestions from the configured provider."""
        revision = self._require_revision(project_id, revision_id)
        # Raises ProviderConfigurationError / ProviderNotConfiguredError;
        # the router maps both to HTTP 501.
        provider = self.registry.create("deepseek", ProviderDependencies())
        described: dict = {}
        describe = getattr(provider, "describe", None)
        if callable(describe):
            described = describe() or {}
        snapshot = build_project_snapshot(project_id, self.data_store)

        def _generate() -> list[WritebackProposalCreate]:
            with timed_operation(
                "provider_call",
                operation="generate_writebacks",
                provider=str(getattr(provider, "name", "unknown")),
                project_id=project_id,
            ):
                return provider.generate_writebacks(revision, snapshot)

        try:
            outcome = self.analysis.run_writeback_generation(
                project_id=project_id,
                source_ref=f"manuscript_revision:{revision.id}",
                processor="deepseek_writeback",
                fingerprint=writeback_input_fingerprint(
                    revision,
                    canon_entities=snapshot.canon_entities,
                    memory_records=snapshot.memory_records,
                    extra={"model": described.get("model", "")},
                ),
                generate=_generate,
                force=force,
            )
        except WritebackPreValidationError:
            # Persisted-proposal validation failure stays a 422 domain error;
            # it must not be swallowed by the generic provider handlers below.
            raise
        except WorkflowNotConfiguredError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        except (ValueError, ValidationError) as exc:
            raise ProviderExecutionError(
                f"Provider returned invalid write-back proposals: {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderExecutionError(f"Provider write-back generation failed: {exc}") from exc
        return outcome

    # -- helpers -----------------------------------------------------------------

    def _require_revision(self, project_id: str, revision_id: str):
        revision = self.data_store.get_manuscript_revision(project_id, revision_id)
        if revision is None:
            raise RevisionNotFoundError("Manuscript revision not found.")
        return revision


def get_writeback_service(
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
    analysis: AnalysisService = Depends(get_analysis_service),
) -> WritebackService:
    return WritebackService(data_store, cognition, analysis)
