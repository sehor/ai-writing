from app.llm.adapters.deepseek import DeepSeekAdapter, DeepSeekSettings, create_deepseek_gateway
from app.llm.adapters.openrouter import (
    OpenRouterAdapter,
    OpenRouterSettings,
    create_openrouter_gateway,
)
from app.llm.capabilities import (
    ModelCapabilities,
    ModelCatalog,
    ModelProfile,
    default_model_catalog,
)
from app.llm.fake import FakeGatewayScenario, FakeModelGateway
from app.llm.gateway import (
    GatewayDescriptor,
    GenerationPolicy,
    ModelGateway,
    ModelGatewayError,
    ModelCompletion,
    ModelRequest,
    ModelResult,
    TokenUsage,
    add_model_call_details,
)
from app.llm.registry import (
    ModelGatewayRegistry,
    default_model_gateway_registry,
    resolve_default_model_gateway,
)
from app.llm.runtime import ModelExecution, ModelRuntime, as_model_runtime


default_model_gateway_registry.register("deepseek", create_deepseek_gateway)
default_model_gateway_registry.register("openrouter", create_openrouter_gateway)


__all__ = [
    "DeepSeekAdapter",
    "DeepSeekSettings",
    "OpenRouterAdapter",
    "OpenRouterSettings",
    "FakeGatewayScenario",
    "FakeModelGateway",
    "GatewayDescriptor",
    "GenerationPolicy",
    "ModelGateway",
    "ModelGatewayError",
    "ModelCompletion",
    "ModelCapabilities",
    "ModelCatalog",
    "ModelExecution",
    "ModelGatewayRegistry",
    "ModelProfile",
    "ModelRequest",
    "ModelResult",
    "ModelRuntime",
    "TokenUsage",
    "add_model_call_details",
    "as_model_runtime",
    "default_model_gateway_registry",
    "default_model_catalog",
    "resolve_default_model_gateway",
]
