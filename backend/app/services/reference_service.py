"""P2-01 application service for reference / copilot suggestions.

Local deterministic generation and provider-backed generation share the
same context assembly; routers only parse requests and map errors.
"""

from app.agents.reference_workflow import (
    build_local_reference_suggestion,
    generate_gateway_reference_suggestion,
    scope_for_request,
)
from app.cognition.registry import CognitionRegistry
from app.cognition.snapshots import build_project_snapshot
from app.data.ports.reference import ReferenceDataPort
from app.narrative import NarrativeSnapshot
from app.llm import (
    ModelGatewayRegistry,
    ModelRuntime,
    default_model_gateway_registry,
)
from app.models import ReferenceGenerationRequest, ReferenceSuggestion
from app.observability import timed_operation
from app.agents.reference_workflow import build_reference_context


class ReferenceService:
    def __init__(
        self,
        data_store: ReferenceDataPort,
        cognition: CognitionRegistry,
        registry: ModelGatewayRegistry | None = None,
    ):
        self.data_store = data_store
        self.cognition = cognition
        self.registry = registry if registry is not None else default_model_gateway_registry

    def list_suggestions(self, project_id: str) -> list[ReferenceSuggestion]:
        return self.data_store.list_reference_suggestions(project_id)

    def _assemble(self, project_id: str, request: ReferenceGenerationRequest):
        if request.scope_type == "scene" and request.scope_ref:
            narrative = NarrativeSnapshot.for_scene(
                project_id=project_id,
                scene_id=request.scope_ref,
                data_store=self.data_store,
                cognition=self.cognition,
            )
            snapshot = narrative.as_project_snapshot()
            cognition_context = narrative.cognition_context
            context = "\n\n".join(
                [
                    build_reference_context(snapshot, request, cognition_context),
                    "## Narrative Snapshot",
                    narrative.render_generation_context(),
                ]
            )
            return snapshot, cognition_context, context

        snapshot = build_project_snapshot(project_id, self.data_store)
        cognition_context = self.cognition.prepare_context(snapshot, scope_for_request(request))
        context = build_reference_context(snapshot, request, cognition_context)
        return snapshot, cognition_context, context

    def generate_local(
        self, project_id: str, request: ReferenceGenerationRequest
    ) -> ReferenceSuggestion:
        snapshot, cognition_context, context = self._assemble(project_id, request)
        with timed_operation(
            "provider_call",
            operation="generate_reference",
            provider="local",
            project_id=project_id,
        ):
            suggestion = build_local_reference_suggestion(
                request, context, snapshot, cognition_context
            )
        return self.data_store.create_reference_suggestion(project_id, suggestion)

    def generate_provider(
        self, project_id: str, request: ReferenceGenerationRequest
    ) -> ReferenceSuggestion:
        snapshot, cognition_context, context = self._assemble(project_id, request)
        generated = generate_gateway_reference_suggestion(
            ModelRuntime(self.registry, recorder=self.data_store),
            request,
            context,
            snapshot,
            cognition_context,
            project_id=project_id,
        )
        return self.data_store.create_reference_suggestion(project_id, generated.suggestion)

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
