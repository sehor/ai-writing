import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.writing_workflow import (
    CanonConstraintChecker,
    LlmWikiContextCollector,
    LocalArtifactNormalizer,
    LocalConsistencyReviewer,
    MemoryRetriever,
    ProjectContextLoader,
    WorkflowAgent,
    WorkflowNotConfiguredError,
    WorkflowProviderError,
    WritingWorkflowState,
)
from app.data import WritingDataStore
from app.llm_wiki.interfaces import LlmWiki
from app.models import (
    CanonEntity,
    MemoryRecord,
    SnowflakeArtifact,
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeStep,
)
from app.text_utils import truncate as truncate_context
from app.snowflake.contracts import STEP_CONTRACTS


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL
    temperature: float = 0.7
    max_tokens: int = 2400

    @classmethod
    def from_env(cls) -> "DeepSeekSettings | None":
        load_project_env()
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            base_url=os.getenv(
                "DEEPSEEK_BASE_URL_FOR_OPENAI",
                os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL),
            ).strip()
            or DEFAULT_DEEPSEEK_BASE_URL,
            model=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip()
            or DEFAULT_DEEPSEEK_MODEL,
            temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "2400")),
        )


class DeepSeekPromptPlanner:
    name = "prompt_planner"
    stage = "pre_generation"

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.record(
            self.stage,
            self.name,
            "planned cache-aware DeepSeek message prefix",
        )
        return state


class DeepSeekDraftGenerator:
    name = "deepseek_draft_generator"
    stage = "generation"

    def __init__(self, settings: DeepSeekSettings):
        self.settings = settings
        self._client: Any | None = None

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        messages = build_deepseek_messages(state)
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
            )
        except WorkflowNotConfiguredError:
            raise
        except Exception as exc:
            raise WorkflowProviderError(
                f"DeepSeek generation failed: {exc}",
                trace=state.trace,
            ) from exc

        content = response.choices[0].message.content if response.choices else ""
        if not content:
            raise WorkflowProviderError(
                "DeepSeek generation returned no content.",
                trace=state.trace,
            )

        state.content = content
        state.record(
            self.stage,
            self.name,
            build_usage_status(response, self.settings.model),
        )
        return state

    @property
    def client(self) -> Any:
        if self._client is None:
            from app.agents.client_factory import get_openai_client

            self._client = get_openai_client(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
            )
        return self._client


class DeepSeekWritingWorkflow:
    def __init__(
        self,
        data_store: WritingDataStore,
        steps: list[SnowflakeStep],
        settings: DeepSeekSettings,
        llm_wiki: LlmWiki,
    ):
        self.agents: list[WorkflowAgent] = [
            ProjectContextLoader(data_store, steps),
            CanonConstraintChecker(data_store),
            MemoryRetriever(data_store),
            LlmWikiContextCollector(llm_wiki),
            DeepSeekPromptPlanner(),
            DeepSeekDraftGenerator(settings),
            LocalConsistencyReviewer(),
            LocalArtifactNormalizer(),
        ]

    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        state = WritingWorkflowState(request=request)
        for agent in self.agents:
            state = agent.run(state)

        return SnowflakeGenerationResponse(
            project_id=request.project_id,
            step_number=request.step_number,
            artifact=state.artifact,
            content=state.content,
            workflow_trace=state.trace,
        )


def create_deepseek_workflow(
    data_store: WritingDataStore,
    steps: list[SnowflakeStep],
    llm_wiki: LlmWiki,
) -> DeepSeekWritingWorkflow | None:
    settings = DeepSeekSettings.from_env()
    if settings is None:
        return None
    return DeepSeekWritingWorkflow(data_store, steps, settings, llm_wiki)


def build_deepseek_messages(state: WritingWorkflowState) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a narrow writing workflow agent inside AI Writing Studio. "
                "Generate Snowflake Method artifacts for long-form fiction. "
                "Respect Canon as confirmed facts. Treat Memory / Style as prose continuity guidance, "
                "not as fact authority. Propose draft content only; the app and human author decide what is saved. "
                "Return only the requested artifact content. Never wrap it in commentary."
            ),
        },
        {
            "role": "user",
            "content": build_stable_context_prefix(state),
        },
        {
            "role": "user",
            "content": build_generation_instruction(state),
        },
    ]


def build_stable_context_prefix(state: WritingWorkflowState) -> str:
    project_title = state.project.title if state.project else state.request.project_id
    premise = state.project.premise if state.project else ""
    step_title = state.step.title if state.step else f"Step {state.request.step_number}"
    step_artifact = state.step.artifact if state.step else "artifact"
    step_description = state.step.description if state.step else ""

    sections = [
        "Stable project context for cache reuse.",
        "",
        "## Project",
        f"Title: {project_title}",
        f"Premise: {premise or 'No premise recorded.'}",
        "",
        "## Active Snowflake Step",
        f"Number: {state.request.step_number}",
        f"Title: {step_title}",
        f"Artifact: {step_artifact}",
        f"Purpose: {step_description}",
        "",
        "## Previous Snowflake Artifacts",
        format_previous_artifacts(
            state.previous_artifacts,
            state.request.previous_artifacts_context_chars,
        ),
        "",
        "## Canon Constraints",
        format_canon_entities(state.canon_entities),
        "",
        "## Memory / Style Context",
        format_memory_records(state.memory_records),
        "",
        "## LLM Wiki Context",
        format_llm_wiki_context(state),
    ]
    return "\n".join(sections)


def build_generation_instruction(state: WritingWorkflowState) -> str:
    step_title = state.step.title if state.step else f"Step {state.request.step_number}"
    artifact = state.step.artifact if state.step else "artifact"
    output_rules = [
        f"Generate the `{artifact}` artifact for Snowflake step {state.request.step_number}: {step_title}.",
        "",
        "## Author Direction",
        state.request.user_input,
        "",
        "## Generation Scope",
        f"Mode: {state.request.generation_mode}",
        f"Base revision: {state.request.base_revision_id or 'none'}",
        "",
        "## Output Contract",
        "- Use dense, author-facing planning prose, not chatty explanation.",
        "- Preserve every explicit Canon constraint from the stable context.",
        "- If information is missing, mark it as `TBD` instead of inventing confirmed facts.",
        "- Keep the result ready for human review and manual save approval.",
    ]
    if state.request.target_records:
        import json

        output_rules.extend(
            [
                "- Revise only these selected records; preserve their record_id values:",
                json.dumps(state.request.target_records, ensure_ascii=False),
            ]
        )
    contract = STEP_CONTRACTS.get(state.request.step_number)
    if contract is not None:
        import json

        output_rules.extend(
            [
                "- Return one JSON object only (no Markdown fence).",
                "- The JSON must validate against this schema:",
                json.dumps(contract.model_json_schema(), ensure_ascii=False),
            ]
        )
    else:
        output_rules.append(f"- Start with `# {step_title}`.")
    if state.request.step_number == 8:
        output_rules.extend(
            [
                "- For each scene, include POV, goal, conflict, turning point, outcome/disaster, required Canon, forbidden facts, information delta, character state delta, and StoryThread actions.",
            ]
        )
    if state.request.step_number == 10:
        output_rules.extend(
            [
                "- Draft prose from available scene contracts and memory/style records.",
                "- Do not alter Canon or claim new facts are confirmed.",
            ]
        )
    return "\n".join(output_rules)


def format_previous_artifacts(
    artifacts: list[SnowflakeArtifact], max_chars: int
) -> str:
    if not artifacts:
        return "No previous artifacts saved."
    context = "\n\n".join(
        "\n".join(
            [
                f"### Step {artifact.step_number}: {artifact.artifact}",
                artifact.content.strip(),
            ]
        )
        for artifact in sorted(
            artifacts,
            key=lambda item: item.step_number,
            reverse=True,
        )
    )
    return truncate_context(context, max_chars)


def format_canon_entities(entities: list[CanonEntity]) -> str:
    if not entities:
        return "No Canon entities recorded."
    return "\n".join(
        f"- {entity.entity_type}: {entity.name} | summary={truncate_context(entity.summary, 500)} "
        f"| current_state={truncate_context(entity.current_state, 900)} "
        f"| constraints={truncate_context(entity.constraints, 900)} "
        f"| last_seen={entity.last_seen or 'unknown'}"
        for entity in entities[:40]
    )


def format_memory_records(records: list[MemoryRecord]) -> str:
    if not records:
        return "No Memory / Style records recorded."
    return "\n\n".join(
        "\n".join(
            [
                f"### {record.record_type}: {record.title}",
                f"Scope: {record.scope or 'global'}",
                f"Tags: {record.tags or 'none'}",
                truncate_context(record.content, 1600),
            ]
        )
        for record in records[:24]
    )


def format_llm_wiki_context(state: WritingWorkflowState) -> str:
    if not state.llm_wiki_context or not state.llm_wiki_context.evidence:
        return "No LLM Wiki evidence available."
    return "\n\n".join(
        "\n".join(
            [
                f"### {evidence.title}",
                f"Source: {evidence.source_ref}",
                truncate_context(evidence.excerpt, 2400),
            ]
        )
        for evidence in state.llm_wiki_context.evidence
    )


def build_usage_status(response: Any, model: str) -> str:
    usage = getattr(response, "usage", None)
    usage_data = usage.model_dump() if hasattr(usage, "model_dump") else usage or {}
    if not isinstance(usage_data, dict):
        return f"called {model}"

    prompt_tokens = usage_data.get("prompt_tokens")
    completion_tokens = usage_data.get("completion_tokens")
    cache_hit = usage_data.get("prompt_cache_hit_tokens")
    cache_miss = usage_data.get("prompt_cache_miss_tokens")
    parts = [f"called {model}"]
    if prompt_tokens is not None:
        parts.append(f"prompt {prompt_tokens}")
    if completion_tokens is not None:
        parts.append(f"completion {completion_tokens}")
    if cache_hit is not None:
        parts.append(f"cache_hit {cache_hit}")
    if cache_miss is not None:
        parts.append(f"cache_miss {cache_miss}")
    return ", ".join(parts)


def combine_prompt(system_prompt: str, user_prompt: str) -> str:
    return f"{system_prompt}\n\n{user_prompt}".strip()


def load_project_env() -> None:
    for env_path in candidate_env_paths():
        if env_path.is_file():
            load_env_file(env_path)
            return


def candidate_env_paths() -> list[Path]:
    paths: list[Path] = []
    for start in [Path.cwd(), Path(__file__).resolve()]:
        for directory in [start, *start.parents]:
            candidate = directory / ".env"
            if candidate not in paths:
                paths.append(candidate)
    return paths


def load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in os.environ:
            continue
        os.environ[key] = value.strip().strip("'\"")
