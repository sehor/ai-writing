"""Application service for model profiles and persisted generation runs."""

from dataclasses import asdict

from fastapi import Depends

from app.data import WritingDataStore, get_data_store
from app.llm import (
    ModelCatalog,
    ModelGatewayError,
    ModelGatewayRegistry,
    default_model_catalog,
    default_model_gateway_registry,
)
from app.models import GenerationRun, ModelCapabilitiesView, ModelProfileView


class ModelService:
    def __init__(
        self,
        data_store: WritingDataStore,
        registry: ModelGatewayRegistry | None = None,
        catalog: ModelCatalog | None = None,
    ) -> None:
        self.data_store = data_store
        self.registry = registry or default_model_gateway_registry
        self.catalog = catalog or default_model_catalog

    def list_profiles(self) -> list[ModelProfileView]:
        result: list[ModelProfileView] = []
        for profile in self.catalog.profiles():
            configured = True
            model_id = profile.model_id
            try:
                gateway = self.registry.create(profile.provider_id, model_id or None)
                described = gateway.describe()
                model_id = described.model_id
            except ModelGatewayError as exc:
                configured = not exc.is_configuration_error
            result.append(
                ModelProfileView(
                    id=profile.id,
                    label=profile.label,
                    provider=profile.provider_id,
                    model=model_id,
                    configured=configured,
                    capabilities=ModelCapabilitiesView(**asdict(profile.capabilities)),
                    fallback_profile_ids=list(profile.fallback_profile_ids),
                )
            )
        return result

    def list_runs(self, project_id: str, limit: int = 50) -> list[GenerationRun]:
        return self.data_store.list_generation_runs(project_id, limit)

    def get_run(self, project_id: str, run_id: str) -> GenerationRun | None:
        return self.data_store.get_generation_run(project_id, run_id)


def get_model_service(
    data_store: WritingDataStore = Depends(get_data_store),
) -> ModelService:
    return ModelService(data_store)


__all__ = ["ModelService", "get_model_service"]
