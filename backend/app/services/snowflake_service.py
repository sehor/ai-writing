"""P2-01 application service for the Snowflake workflow.

Owns runtime-status reporting, artifact persistence with transactional
Wiki-index outbox enqueueing, and generation orchestration. Routers stay
pure HTTP: they parse requests, call this service, and map domain errors.
Since P1-03 this service only enqueues index jobs; executing them is the
job of the app-owned outbox dispatcher, which routes wake after enqueuing.
"""

from typing import Any

from fastapi import Depends

from app.data import WritingDataStore, get_data_store
from app.integrations.provider_registry import (
    ProviderDependencies,
    ProviderConfigurationError,
    ProviderNotConfiguredError,
    ProviderRegistry,
    ProviderSnowflakeWorkflow,
    default_provider_registry,
    resolve_default_provider,
)
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import LlmWiki, WikiSourceDocument
from app.models import (
    SnowflakeArtifact,
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeStep,
    WorkflowRuntimeStatus,
)
from app.outbox.handlers import snowflake_index_payload
from app.agents.writing_workflow import WritingWorkflow


SNOWFLAKE_STEPS = [
    SnowflakeStep(
        number=1,
        title="One Sentence",
        artifact="story_contract",
        description="Distill the novel into a single sentence promise.",
    ),
    SnowflakeStep(
        number=2,
        title="One Paragraph",
        artifact="plot_seed",
        description="Expand the story promise into a compact beginning, middle, and end.",
    ),
    SnowflakeStep(
        number=3,
        title="Character Summary",
        artifact="character_seeds",
        description="Create initial goals, conflicts, secrets, and arcs for major characters.",
    ),
    SnowflakeStep(
        number=4,
        title="One Page Synopsis",
        artifact="plot_synopsis",
        description="Compile the story into a one-page plot outline.",
    ),
    SnowflakeStep(
        number=5,
        title="Character Viewpoints",
        artifact="character_pov_lines",
        description="Describe the story from each major character's perspective.",
    ),
    SnowflakeStep(
        number=6,
        title="Expanded Synopsis",
        artifact="expanded_plot",
        description="Expand the plot into a multi-page causal outline.",
    ),
    SnowflakeStep(
        number=7,
        title="Character Bible",
        artifact="canon_entities",
        description="Commit character, location, item, and faction facts into Canon.",
    ),
    SnowflakeStep(
        number=8,
        title="Scene List",
        artifact="scene_contracts",
        description="Compile the plot into scene contracts with goals, conflicts, turns, and constraints.",
    ),
    SnowflakeStep(
        number=9,
        title="Scene Expansion",
        artifact="expanded_scenes",
        description="Expand each scene contract into detailed beats and chapter plans.",
    ),
    SnowflakeStep(
        number=10,
        title="Draft Manuscript",
        artifact="manuscript",
        description="Draft prose from scene contracts, Canon constraints, memory, and style samples.",
    ),
]


class StepNotFoundError(LookupError):
    pass


class ArtifactNotFoundError(LookupError):
    pass


class SnowflakeService:
    def __init__(
        self,
        data_store: WritingDataStore,
        llm_wiki: LlmWiki,
        registry: ProviderRegistry | None = None,
    ):
        self.data_store = data_store
        self.llm_wiki = llm_wiki
        self.registry = registry if registry is not None else default_provider_registry

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
            provider = self.registry.create("deepseek", ProviderDependencies())
        except ProviderConfigurationError as exc:
            return WorkflowRuntimeStatus(
                runtime="local_deterministic",
                provider="local",
                provider_configured=False,
                details=f"DeepSeek environment is invalid: {exc}",
            )
        except ProviderNotConfiguredError:
            return WorkflowRuntimeStatus(
                runtime="local_deterministic",
                provider="local",
                provider_configured=False,
                details="DEEPSEEK_API_KEY is not configured; using deterministic local drafts.",
            )
        described: dict[str, Any] = {}
        describe = getattr(provider, "describe", None)
        if callable(describe):
            described = describe() or {}
        return WorkflowRuntimeStatus(
            runtime="provider_deepseek",
            provider="deepseek",
            provider_configured=True,
            model=described.get("model", ""),
            base_url=described.get("base_url", ""),
            details="DeepSeek provider runtime is configured for Snowflake draft generation.",
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

    def save_artifact(
        self, project_id: str, step_number: int, content: str
    ) -> tuple[SnowflakeArtifact, str | None]:
        """Persist an artifact and enqueue its Wiki-index job (one transaction).

        Returns the artifact plus the enqueued job id; executing the job is
        the dispatcher's business (P1-03), not this request's.
        """
        step = self.get_step(step_number)
        artifact = SnowflakeArtifact(
            project_id=project_id,
            step_number=step_number,
            artifact=step.artifact,
            content=content,
        )
        return self.data_store.enqueue_snowflake_index_job(
            artifact, advance_step_to=step_number
        )

    def generate(
        self, request: SnowflakeGenerationRequest, workflow: WritingWorkflow
    ) -> tuple[SnowflakeGenerationResponse, str | None]:
        """Run one generation workflow, then enqueue its indexing job."""
        self.get_step(request.step_number)
        generated = workflow.run_snowflake_generation(request)
        _, job_id = self.data_store.enqueue_snowflake_index_job(
            SnowflakeArtifact(
                project_id=generated.project_id,
                step_number=generated.step_number,
                artifact=generated.artifact,
                content=generated.content,
            ),
            advance_step_to=request.step_number,
        )
        return generated, job_id


# ---------------------------------------------------------------------------
# FastAPI wiring shared by routers and tests
# ---------------------------------------------------------------------------


def get_snowflake_service(
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> SnowflakeService:
    return SnowflakeService(data_store, llm_wiki)


def get_writing_workflow(
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> WritingWorkflow:
    """Resolve the configured provider behind the app-owned workflow interface."""
    provider, _skip_reason = resolve_default_provider(ProviderDependencies())
    return ProviderSnowflakeWorkflow(provider, data_store, SNOWFLAKE_STEPS, llm_wiki)


def snowflake_wiki_document(artifact: SnowflakeArtifact) -> WikiSourceDocument:
    """Kept for compatibility; the mapping now lives in app.outbox.handlers."""
    return WikiSourceDocument.model_validate(snowflake_index_payload(artifact))
