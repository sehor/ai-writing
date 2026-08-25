"""P2-02 provider registry.

Every AI generation backend registers behind one interface
(WritingProvider). Adding a new provider means:

1. implement the protocol,
2. register a factory on the registry,
3. flip configuration (environment or code).

Routers and application services never import concrete runtimes
(DeepSeekSettings, OpenAI SDK clients, HermesAgentClient); they ask
the registry for a provider by name or resolve the configured default.
"""

from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

from app.agents.deepseek_workflow import DeepSeekSettings, DeepSeekWritingWorkflow
from app.agents.manuscript_workflow import build_provider_scene_draft
from app.agents.reference_workflow import (
    build_local_reference_suggestion,
    build_provider_reference_suggestion,
)
from app.agents.writeback_workflow import build_provider_writeback_proposals
from app.agents.writing_workflow import LocalDraftWritingWorkflow
from app.cognition.interfaces import (
    CommittedContentEvent,
    ContextPacket,
    ProjectCognitionSnapshot,
)
from app.data import WritingDataStore
from app.llm_wiki.interfaces import LlmWiki
from app.models import (
    ManuscriptRevision,
    ReferenceGenerationRequest,
    ReferenceSuggestionCreate,
    SceneContract,
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeStep,
    WritebackProposalCreate,
)
from app.services.compile_service import build_scene_draft


class ProviderNotConfiguredError(LookupError):
    """The provider exists but has no usable configuration (no API key)."""

    def __init__(self, provider_name: str):
        super().__init__(f"Provider '{provider_name}' is not configured.")
        self.provider_name = provider_name


class ProviderConfigurationError(ValueError):
    """Provider configuration exists but is invalid (bad env values, missing SDK)."""

    def __init__(self, provider_name: str, cause: str):
        super().__init__(cause)
        self.provider_name = provider_name
        self.cause_text = cause


class ProviderExecutionError(RuntimeError):
    """A configured provider failed while generating output."""


class ProviderUnavailableError(RuntimeError):
    """A configured provider cannot run right now (for example missing SDK)."""


class WritingProvider(Protocol):
    """One interface for every generation backend.

    Implementations stay narrow: they turn app-owned requests and
    already-built context into proposed content. They never touch review
    state and never commit project data.
    """

    name: str

    def generate_snowflake(
        self,
        request: SnowflakeGenerationRequest,
        *,
        data_store: WritingDataStore,
        steps: Sequence[SnowflakeStep],
        llm_wiki: LlmWiki,
    ) -> SnowflakeGenerationResponse: ...

    def generate_manuscript(self, scene: SceneContract, context: str) -> str: ...

    def generate_reference(
        self,
        request: ReferenceGenerationRequest,
        *,
        context: str,
        snapshot: ProjectCognitionSnapshot,
        cognition_context: list[ContextPacket],
    ) -> ReferenceSuggestionCreate: ...

    def generate_writebacks(
        self,
        revision: ManuscriptRevision,
        snapshot: ProjectCognitionSnapshot,
    ) -> list[WritebackProposalCreate]: ...


@dataclass(frozen=True)
class ProviderDependencies:
    """Per-request dependencies a provider factory may need.

    Snowflake-capable providers receive store/wiki/steps at call time;
    factories mainly need cognition for the deterministic local extractor.
    """

    cognition: Any | None = None


class LocalDeterministicProvider:
    """Deterministic offline fallback registered under the local name."""

    name = "local"
    runtime_label = "local_deterministic"

    def __init__(self, cognition: Any | None = None):
        self.cognition = cognition

    def generate_snowflake(
        self,
        request: SnowflakeGenerationRequest,
        *,
        data_store: WritingDataStore,
        steps: Sequence[SnowflakeStep],
        llm_wiki: LlmWiki,
    ) -> SnowflakeGenerationResponse:
        workflow = LocalDraftWritingWorkflow(data_store, list(steps), llm_wiki)
        return workflow.run_snowflake_generation(request)

    def generate_manuscript(self, scene: SceneContract, context: str) -> str:
        return build_scene_draft(scene)

    def generate_reference(
        self,
        request: ReferenceGenerationRequest,
        *,
        context: str,
        snapshot: ProjectCognitionSnapshot,
        cognition_context: list[ContextPacket],
    ) -> ReferenceSuggestionCreate:
        return build_local_reference_suggestion(request, context, snapshot, cognition_context)

    def generate_writebacks(
        self,
        revision: ManuscriptRevision,
        snapshot: ProjectCognitionSnapshot,
    ) -> list[WritebackProposalCreate]:
        if self.cognition is None:
            raise ProviderNotConfiguredError(self.name)
        event = CommittedContentEvent(
            source="manuscript_revision",
            source_ref=f"manuscript_revision:{revision.id}",
            title=revision.title,
            content=revision.content,
            revision=revision,
        )
        reports = self.cognition.ingest_committed_content(snapshot, event)
        return [proposal for report in reports for proposal in report.writeback_proposals]

    def describe(self) -> dict[str, Any]:
        return {}


class DeepSeekProvider:
    """OpenAI-compatible DeepSeek runtime registered under the deepseek name."""

    name = "deepseek"
    runtime_label = "provider_deepseek"

    def __init__(self, settings: DeepSeekSettings):
        self.settings = settings

    def generate_snowflake(
        self,
        request: SnowflakeGenerationRequest,
        *,
        data_store: WritingDataStore,
        steps: Sequence[SnowflakeStep],
        llm_wiki: LlmWiki,
    ) -> SnowflakeGenerationResponse:
        workflow = DeepSeekWritingWorkflow(data_store, list(steps), self.settings, llm_wiki)
        return workflow.run_snowflake_generation(request)

    def generate_manuscript(self, scene: SceneContract, context: str) -> str:
        return build_provider_scene_draft(self.settings, context)

    def generate_reference(
        self,
        request: ReferenceGenerationRequest,
        *,
        context: str,
        snapshot: ProjectCognitionSnapshot,
        cognition_context: list[ContextPacket],
    ) -> ReferenceSuggestionCreate:
        return build_provider_reference_suggestion(
            self.settings, request, context, snapshot, cognition_context
        )

    def generate_writebacks(
        self,
        revision: ManuscriptRevision,
        snapshot: ProjectCognitionSnapshot,
    ) -> list[WritebackProposalCreate]:
        return build_provider_writeback_proposals(
            self.settings,
            revision,
            snapshot.canon_entities,
            snapshot.memory_records,
        )

    def describe(self) -> dict[str, Any]:
        return {"model": self.settings.model, "base_url": self.settings.base_url}


ProviderFactory = Callable[[ProviderDependencies], "WritingProvider | None"]


def create_deepseek_provider(deps: ProviderDependencies) -> DeepSeekProvider | None:
    try:
        settings = DeepSeekSettings.from_env()
    except ValueError as exc:
        raise ProviderConfigurationError("deepseek", str(exc)) from exc
    if settings is None:
        return None
    return DeepSeekProvider(settings)


def create_local_provider(deps: ProviderDependencies) -> LocalDeterministicProvider:
    return LocalDeterministicProvider(cognition=deps.cognition)


DEFAULT_PROVIDER_PRIORITY: tuple[str, ...] = ("deepseek", "local")


class ProviderRegistry:
    """Named registry of provider factories with explicit resolution order."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        self._factories[name] = factory

    def names(self) -> list[str]:
        return sorted(self._factories)

    def has(self, name: str) -> bool:
        return name in self._factories

    def create(self, name: str, deps: ProviderDependencies) -> WritingProvider:
        """Build a ready-to-use provider.

        Raises ProviderNotConfiguredError when the backend has no usable
        configuration and ProviderConfigurationError when the configuration
        itself is invalid.
        """
        factory = self._factories.get(name)
        if factory is None:
            raise ProviderNotConfiguredError(name)
        try:
            provider = factory(deps)
        except (ProviderConfigurationError, ProviderNotConfiguredError):
            raise
        if provider is None:
            raise ProviderNotConfiguredError(name)
        return provider

    def configuration_problem(self, name: str, deps: ProviderDependencies) -> str | None:
        """Return why the named provider cannot serve requests now, else None."""
        try:
            self.create(name, deps)
        except ProviderConfigurationError as exc:
            return exc.cause_text
        except ProviderNotConfiguredError:
            return f"{name} provider is not configured."
        return None


default_provider_registry = ProviderRegistry()
default_provider_registry.register("deepseek", create_deepseek_provider)
default_provider_registry.register("local", create_local_provider)


def resolve_default_provider(
    deps: ProviderDependencies,
    registry: ProviderRegistry | None = None,
    priority: Sequence[str] = DEFAULT_PROVIDER_PRIORITY,
) -> tuple[WritingProvider, str | None]:
    """First configured provider in priority order wins.

    Returns the provider plus the skip reason recorded for higher-priority
    backends (None when the first choice was used). Register an always
    available fallback (local) so this never fails in practice.
    """
    active = registry if registry is not None else default_provider_registry
    skip_reasons: list[str] = []
    for name in priority:
        try:
            provider = active.create(name, deps)
        except ProviderConfigurationError as exc:
            skip_reasons.append(f"{name}: invalid configuration ({exc})")
            continue
        except ProviderNotConfiguredError:
            skip_reasons.append(f"{name}: not configured")
            continue
        return provider, "; ".join(skip_reasons) if skip_reasons else None
    raise ProviderNotConfiguredError(",".join(priority))


class ProviderSnowflakeWorkflow:
    """Adapt a WritingProvider to the app-owned WritingWorkflow interface.

    Keeps workflow-level call sites (and tests that override the workflow
    dependency) working unchanged above the registry.
    """

    def __init__(
        self,
        provider: WritingProvider,
        data_store: WritingDataStore,
        steps: Sequence[SnowflakeStep],
        llm_wiki: LlmWiki,
    ):
        self.provider = provider
        self.data_store = data_store
        self.steps = list(steps)
        self.llm_wiki = llm_wiki

    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        return self.provider.generate_snowflake(
            request,
            data_store=self.data_store,
            steps=self.steps,
            llm_wiki=self.llm_wiki,
        )
