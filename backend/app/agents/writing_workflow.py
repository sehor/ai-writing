from dataclasses import dataclass, field
from typing import Protocol

from app.data import WritingDataStore
from app.llm_wiki.interfaces import LlmWiki, WikiContextQuery, WikiContextResult
from app.models import (
    CanonEntity,
    MemoryRecord,
    ProjectSummary,
    SnowflakeArtifact,
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    SnowflakeStep,
    WorkflowAgentTrace,
)


class WorkflowNotConfiguredError(RuntimeError):
    def __init__(self, message: str, trace: list[WorkflowAgentTrace] | None = None):
        super().__init__(message)
        self.trace = trace or []


class WorkflowProviderError(RuntimeError):
    def __init__(self, message: str, trace: list[WorkflowAgentTrace] | None = None):
        super().__init__(message)
        self.trace = trace or []


@dataclass
class WritingWorkflowState:
    request: SnowflakeGenerationRequest
    project: ProjectSummary | None = None
    step: SnowflakeStep | None = None
    previous_artifacts: list[SnowflakeArtifact] = field(default_factory=list)
    canon_entities: list[CanonEntity] = field(default_factory=list)
    memory_records: list[MemoryRecord] = field(default_factory=list)
    llm_wiki_context: WikiContextResult | None = None
    artifact: str = ""
    content: str = ""
    trace: list[WorkflowAgentTrace] = field(default_factory=list)

    def record(self, stage: str, agent_name: str, status: str) -> None:
        self.trace.append(
            WorkflowAgentTrace(stage=stage, agent_name=agent_name, status=status)
        )


class WorkflowAgent(Protocol):
    name: str
    stage: str

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        pass


class WritingWorkflow(Protocol):
    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        pass


class InterfaceOnlyWorkflowAgent:
    def __init__(self, name: str, stage: str):
        self.name = name
        self.stage = stage

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.record(self.stage, self.name, "declared")
        return state


class InterfaceOnlyWritingWorkflow:
    def __init__(self) -> None:
        self.pre_generation_agents: list[WorkflowAgent] = [
            InterfaceOnlyWorkflowAgent("project_context_loader", "pre_generation"),
            InterfaceOnlyWorkflowAgent("canon_constraint_checker", "pre_generation"),
            InterfaceOnlyWorkflowAgent("memory_retriever", "pre_generation"),
            InterfaceOnlyWorkflowAgent("prompt_planner", "pre_generation"),
        ]
        self.generation_agents: list[WorkflowAgent] = [
            InterfaceOnlyWorkflowAgent("draft_generator", "generation"),
        ]
        self.post_generation_agents: list[WorkflowAgent] = [
            InterfaceOnlyWorkflowAgent("consistency_reviewer", "post_generation"),
            InterfaceOnlyWorkflowAgent("style_reviewer", "post_generation"),
            InterfaceOnlyWorkflowAgent("artifact_normalizer", "post_generation"),
        ]

    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        state = WritingWorkflowState(request=request)
        for agent in (
            self.pre_generation_agents
            + self.generation_agents
            + self.post_generation_agents
        ):
            state = agent.run(state)

        raise WorkflowNotConfiguredError(
            "Writing workflow implementation is not configured.",
            trace=state.trace,
        )


class ProjectContextLoader:
    name = "project_context_loader"
    stage = "pre_generation"

    def __init__(self, data_store: WritingDataStore, steps: list[SnowflakeStep]):
        self.data_store = data_store
        self.steps = steps

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.project = self.data_store.get_project(state.request.project_id)
        state.step = next(
            (step for step in self.steps if step.number == state.request.step_number),
            None,
        )
        state.previous_artifacts = [
            artifact
            for artifact in self.data_store.list_snowflake_artifacts(
                state.request.project_id
            )
            if artifact.step_number < state.request.step_number
        ]
        state.artifact = state.step.artifact if state.step else ""
        state.record(self.stage, self.name, "loaded")
        return state


class CanonConstraintChecker:
    name = "canon_constraint_checker"
    stage = "pre_generation"

    def __init__(self, data_store: WritingDataStore):
        self.data_store = data_store

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.canon_entities = self.data_store.list_canon_entities(state.request.project_id)
        state.record(self.stage, self.name, f"loaded {len(state.canon_entities)} entities")
        return state


class MemoryRetriever:
    name = "memory_retriever"
    stage = "pre_generation"

    def __init__(self, data_store: WritingDataStore):
        self.data_store = data_store

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.memory_records = self.data_store.list_memory_records(state.request.project_id)
        state.record(self.stage, self.name, f"loaded {len(state.memory_records)} records")
        return state


class PromptPlanner:
    name = "prompt_planner"
    stage = "pre_generation"

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.record(self.stage, self.name, "planned deterministic development draft")
        return state


class LlmWikiContextCollector:
    name = "llm_wiki_context_collector"
    stage = "pre_generation"

    def __init__(self, llm_wiki: LlmWiki):
        self.llm_wiki = llm_wiki

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.llm_wiki_context = self.llm_wiki.retrieve_context(
            WikiContextQuery(
                project_id=state.request.project_id,
                snowflake_step=state.request.step_number,
                instruction=state.request.user_input,
            )
        )
        state.record(
            self.stage,
            self.name,
            (
                f"loaded {len(state.llm_wiki_context.evidence)} "
                "stage-aware evidence records"
            ),
        )
        return state


class LocalDraftGenerator:
    name = "draft_generator"
    stage = "generation"

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.content = build_local_draft(state)
        state.record(self.stage, self.name, "drafted")
        return state


class LocalConsistencyReviewer:
    name = "consistency_reviewer"
    stage = "post_generation"

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.record(self.stage, self.name, "checked against loaded canon")
        return state


class LocalArtifactNormalizer:
    name = "artifact_normalizer"
    stage = "post_generation"

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.content = state.content.strip()
        state.record(self.stage, self.name, "normalized")
        return state


class LocalDraftWritingWorkflow:
    def __init__(
        self,
        data_store: WritingDataStore,
        steps: list[SnowflakeStep],
        llm_wiki: LlmWiki,
    ):
        self.agents: list[WorkflowAgent] = [
            ProjectContextLoader(data_store, steps),
            CanonConstraintChecker(data_store),
            MemoryRetriever(data_store),
            LlmWikiContextCollector(llm_wiki),
            PromptPlanner(),
            LocalDraftGenerator(),
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


def build_local_draft(state: WritingWorkflowState) -> str:
    project_title = state.project.title if state.project else state.request.project_id
    premise = state.project.premise if state.project else ""
    step_title = state.step.title if state.step else f"Step {state.request.step_number}"
    artifact = state.step.artifact if state.step else "artifact"
    previous_context = "\n".join(
        f"- Step {item.step_number} `{item.artifact}`: {summarize(item.content)}"
        for item in state.previous_artifacts[-3:]
    )
    canon_context = "\n".join(
        f"- {item.entity_type}: {item.name} | {summarize(item.constraints or item.current_state or item.summary)}"
        for item in state.canon_entities[:8]
    )
    memory_context = "\n".join(
        f"- {item.record_type}: {item.title} | {summarize(item.content)}"
        for item in state.memory_records[:8]
    )

    sections = [
        f"# {step_title}",
        f"Artifact: `{artifact}`",
        "",
        "## Project",
        f"Title: {project_title}",
        f"Premise: {premise or 'No premise recorded.'}",
        "",
        "## Author Direction",
        state.request.user_input,
    ]
    if previous_context:
        sections.extend(["", "## Upstream Snowflake Context", previous_context])
    if canon_context:
        sections.extend(["", "## Canon Constraints", canon_context])
    if memory_context:
        sections.extend(["", "## Memory / Style Context", memory_context])
    if state.llm_wiki_context and state.llm_wiki_context.evidence:
        sections.extend(
            [
                "",
                "## LLM Wiki Context",
                format_llm_wiki_context(state.llm_wiki_context),
            ]
        )
    sections.extend(
        [
            "",
            "## Development Draft",
            draft_for_step(state.request.step_number, premise, state.request.user_input),
            "",
            "## Review Checklist",
            "- Confirm the artifact matches the active Snowflake step.",
            "- Check that Canon constraints above are not contradicted.",
            "- Save only after human review.",
        ]
    )
    return "\n".join(sections)


def draft_for_step(step_number: int, premise: str, user_input: str) -> str:
    source = user_input or premise
    if step_number == 1:
        return f"{single_line(source)}"
    if step_number == 8:
        return "\n".join(
            [
                "Scene 1",
                f"- POV: TBD",
                f"- Goal: {single_line(source)}",
                "- Conflict: Define the immediate opposition.",
                "- Turning point: Define the irreversible change.",
                "- Required Canon: Link confirmed entities before drafting.",
                "- Forbidden facts: List information that cannot be revealed yet.",
                "- Open threads: List questions this scene opens or advances.",
            ]
        )
    return (
        "Use this as a structured development draft. Expand it into the requested "
        f"Snowflake artifact while preserving the project premise: {single_line(source)}"
    )


def summarize(value: str, limit: int = 240) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 3]}..."


def single_line(value: str) -> str:
    text = summarize(value, 360)
    return text if text.endswith((".", "!", "?")) else f"{text}."


def format_llm_wiki_context(context: WikiContextResult) -> str:
    return "\n\n".join(
        "\n".join(
            [
                f"### {evidence.title}",
                f"Source: {evidence.source_ref}",
                summarize(evidence.excerpt, 1600),
            ]
        )
        for evidence in context.evidence
    )
