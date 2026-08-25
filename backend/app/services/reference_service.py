"""P2-01 application service for reference / copilot suggestions.

Local deterministic generation and provider-backed generation share the
same context assembly; routers only parse requests and map errors.
"""

from fastapi import Depends

from app.agents.reference_workflow import scope_for_request
from app.agents.writing_workflow import WorkflowNotConfiguredError
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store
from app.integrations.provider_registry import (
    LocalDeterministicProvider,
    ProviderDependencies,
    ProviderExecutionError,
    ProviderRegistry,
    ProviderUnavailableError,
    default_provider_registry,
)
from app.models import ReferenceGenerationRequest, ReferenceSuggestion
from app.agents.reference_workflow import build_reference_context


class ReferenceService:
    def __init__(
        self,
        data_store: WritingDataStore,
        cognition: CognitionRegistry,
        registry: ProviderRegistry | None = None,
    ):
        self.data_store = data_store
        self.cognition = cognition
        self.registry = registry if registry is not None else default_provider_registry

    def list_suggestions(self, project_id: str) -> list[ReferenceSuggestion]:
        return self.data_store.list_reference_suggestions(project_id)

    def _assemble(self, project_id: str, request: ReferenceGenerationRequest):
        snapshot = build_project_snapshot(project_id, self.data_store)
        cognition_context = self.cognition.prepare_context(snapshot, scope_for_request(request))
        context = build_reference_context(snapshot, request, cognition_context)
        return snapshot, cognition_context, context

    def generate_local(
        self, project_id: str, request: ReferenceGenerationRequest
    ) -> ReferenceSuggestion:
        snapshot, cognition_context, context = self._assemble(project_id, request)
        provider = LocalDeterministicProvider(cognition=self.cognition)
        suggestion = provider.generate_reference(
            request,
            context=context,
            snapshot=snapshot,
            cognition_context=cognition_context,
        )
        return self.data_store.create_reference_suggestion(project_id, suggestion)

    def generate_provider(
        self, project_id: str, request: ReferenceGenerationRequest
    ) -> ReferenceSuggestion:
        # Raises ProviderConfigurationError / ProviderNotConfiguredError;
        # the router maps both to HTTP 501.
        provider = self.registry.create("deepseek", ProviderDependencies())
        snapshot, cognition_context, context = self._assemble(project_id, request)
        try:
            suggestion = provider.generate_reference(
                request,
                context=context,
                snapshot=snapshot,
                cognition_context=cognition_context,
            )
        except WorkflowNotConfiguredError as exc:
            raise ProviderUnavailableError(str(exc)) from exc
        except Exception as exc:
            raise ProviderExecutionError(f"Provider reference generation failed: {exc}") from exc
        return self.data_store.create_reference_suggestion(project_id, suggestion)

    def update_status(
        self, project_id: str, suggestion_id: str, status_str: str
    ) -> ReferenceSuggestion | None:
        """Returns None when the suggestion does not exist.

        Raises ValueError on illegal review transitions (router maps to 409).
        """
        return self.data_store.update_reference_suggestion_status(
            project_id,
            suggestion_id,
            status_str,
        )


__all__ = [
    "ReferenceService",
]


def get_reference_service(
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> ReferenceService:
    return ReferenceService(data_store, cognition)
