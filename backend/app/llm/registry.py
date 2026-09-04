"""Registry for remote model gateway adapters only."""

from collections.abc import Callable, Sequence
from inspect import signature

from app.llm.gateway import ModelGateway, ModelGatewayError


ModelGatewayFactory = Callable[[str | None], ModelGateway | None]
DEFAULT_GATEWAY_PRIORITY: tuple[str, ...] = ("deepseek", "openrouter")


class ModelGatewayRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ModelGatewayFactory] = {}

    def register(self, name: str, factory: Callable[..., ModelGateway | None]) -> None:
        if not signature(factory).parameters:
            self._factories[name] = lambda _model_id: factory()
        else:
            self._factories[name] = factory

    def names(self) -> list[str]:
        return sorted(self._factories)

    def has(self, name: str) -> bool:
        return name in self._factories

    def create(self, name: str, model_id: str | None = None) -> ModelGateway:
        factory = self._factories.get(name)
        if factory is None:
            raise ModelGatewayError(
                "not_configured",
                f"Model gateway '{name}' is not registered.",
                provider_id=name,
            )
        try:
            gateway = factory(model_id)
        except ModelGatewayError:
            raise
        except ValueError as exc:
            raise ModelGatewayError(
                "configuration",
                f"Model gateway '{name}' configuration is invalid.",
                provider_id=name,
            ) from exc
        if gateway is None:
            raise ModelGatewayError(
                "not_configured",
                f"Model gateway '{name}' is not configured.",
                provider_id=name,
            )
        return gateway

    def configuration_problem(self, name: str, model_id: str | None = None) -> str | None:
        try:
            self.create(name, model_id)
        except ModelGatewayError as exc:
            if exc.is_configuration_error:
                return exc.safe_message
            raise
        return None


def resolve_default_model_gateway(
    registry: ModelGatewayRegistry | None = None,
    priority: Sequence[str] = DEFAULT_GATEWAY_PRIORITY,
) -> tuple[ModelGateway, str | None]:
    active = registry if registry is not None else default_model_gateway_registry
    problems: list[str] = []
    for name in priority:
        try:
            return active.create(name), "; ".join(problems) if problems else None
        except ModelGatewayError as exc:
            if not exc.is_configuration_error:
                raise
            problems.append(f"{name}: {exc.safe_message}")
    raise ModelGatewayError(
        "not_configured",
        "No remote model gateway is configured.",
        provider_id=",".join(priority),
    )


default_model_gateway_registry = ModelGatewayRegistry()
