from dataclasses import dataclass, field
import json
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
    SnowflakeRecordRevision,
    SnowflakeStep,
    SnowflakeValidationReport,
    WorkflowAgentTrace,
)
from app.prompts.snowflake import select_relevant_upstream_records
from app.prompts.models import PromptPlan
from app.text_utils import truncate as summarize
from app.snowflake.validators import (
    validate_snowflake_payload,
    validate_snowflake_canon_consistency,
    validate_snowflake_record_generation,
)


class WorkflowNotConfiguredError(RuntimeError):
    def __init__(self, message: str, trace: list[WorkflowAgentTrace] | None = None):
        super().__init__(message)
        self.trace = trace or []


@dataclass
class WritingWorkflowState:
    request: SnowflakeGenerationRequest
    project: ProjectSummary | None = None
    step: SnowflakeStep | None = None
    previous_artifacts: list[SnowflakeArtifact] = field(default_factory=list)
    previous_records: dict[int, list[SnowflakeRecordRevision]] = field(default_factory=dict)
    canon_entities: list[CanonEntity] = field(default_factory=list)
    memory_records: list[MemoryRecord] = field(default_factory=list)
    llm_wiki_context: WikiContextResult | None = None
    artifact: str = ""
    content: str = ""
    trace: list[WorkflowAgentTrace] = field(default_factory=list)
    validation_report: SnowflakeValidationReport | None = None
    prompt_plan: PromptPlan | None = None

    def record(
        self,
        stage: str,
        agent_name: str,
        status: str,
        *,
        finding_count: int = 0,
        details: str = "",
        prompt_id: str = "",
        prompt_version: str = "",
        schema_name: str = "",
        schema_version: str = "",
        provider_id: str = "",
        model_id: str = "",
        finish_reason: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        generation_run_id: str = "",
        attempt_count: int = 0,
        repair_count: int = 0,
        fallback_count: int = 0,
    ) -> None:
        self.trace.append(
            WorkflowAgentTrace(
                stage=stage,
                agent_name=agent_name,
                status=status,
                finding_count=finding_count,
                details=details,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                schema_name=schema_name,
                schema_version=schema_version,
                provider_id=provider_id,
                model_id=model_id,
                finish_reason=finish_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                generation_run_id=generation_run_id,
                attempt_count=attempt_count,
                repair_count=repair_count,
                fallback_count=fallback_count,
            )
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
            self.pre_generation_agents + self.generation_agents + self.post_generation_agents
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
            for artifact in self.data_store.list_snowflake_artifacts(state.request.project_id)
            if artifact.step_number < state.request.step_number
            and artifact.step_number not in {6, 7, 8, 9}
        ]
        state.previous_records = {
            step_number: records
            for step_number in range(6, min(state.request.step_number, 10))
            if (
                records := self.data_store.list_accepted_snowflake_records(
                    state.request.project_id, step_number
                )
            )
        }
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
        state.record(
            self.stage,
            self.name,
            f"loaded {len(state.canon_entities)} entities for generation and review",
        )
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
            (f"loaded {len(state.llm_wiki_context.evidence)} stage-aware evidence records"),
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
        if state.request.step_number in {6, 7, 8, 9}:
            _records, report = validate_snowflake_record_generation(
                state.request.step_number,
                state.content,
                state.request.target_record_ids or None,
            )
        else:
            report = validate_snowflake_payload(state.request.step_number, state.content)
        canon_report = validate_snowflake_canon_consistency(
            state.request.step_number,
            state.content,
            state.canon_entities,
        )
        findings = [*report.findings, *canon_report.findings]
        if report.status == "failed":
            status = "failed"
        elif findings:
            status = "warnings"
        else:
            status = "passed"
        state.validation_report = SnowflakeValidationReport(
            step_number=state.request.step_number,
            status=status,
            findings=findings,
        )
        state.record(
            self.stage,
            self.name,
            status,
            finding_count=len(findings),
            details="Snowflake contract and accepted-Canon consistency checks executed.",
        )
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
            validation_report=state.validation_report,
        )


def build_local_draft(state: WritingWorkflowState) -> str:
    if state.request.target_records:
        return json.dumps(
            {
                "records": [
                    {
                        "record_id": record["record_id"],
                        "payload": record["payload"],
                    }
                    for record in state.request.target_records
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    if state.request.step_number in {6, 7, 8, 9}:
        record_id, payload = draft_record_for_step(
            state.request.step_number,
            state.project.premise if state.project else "",
            state.request.user_input,
        )
        return json.dumps(
            {"records": [{"record_id": record_id, "payload": payload}]},
            ensure_ascii=False,
            indent=2,
        )
    project_title = state.project.title if state.project else state.request.project_id
    premise = state.project.premise if state.project else ""
    step_title = state.step.title if state.step else f"Step {state.request.step_number}"
    artifact = state.step.artifact if state.step else "artifact"
    previous_context = "\n".join(
        f"- Step {item.step_number} `{item.artifact}`: {summarize(item.content)}"
        for item in state.previous_artifacts[-3:]
    )
    relevant_records = select_relevant_upstream_records(state)
    if relevant_records:
        previous_context = "\n".join(
            [
                previous_context,
                *(
                    f"- Step {record.step_number} record `{record.record_id}`: "
                    f"{summarize(json.dumps(record.payload, ensure_ascii=False), 1200)}"
                    for record in relevant_records[:12]
                ),
            ]
        ).strip()
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
        "",
        "## Generation Scope",
        f"Mode: {state.request.generation_mode}",
        f"Base revision: {state.request.base_revision_id or 'none'}",
    ]
    if state.request.target_records:
        sections.extend(["", "## Selected Records", json.dumps(state.request.target_records, ensure_ascii=False)])
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
    if step_number == 2:
        return json.dumps(
            {
                name: {
                    "beat_id": name,
                    "event": single_line(source) if name == "setup" else f"Develop the {name.replace('_', ' ')}.",
                    "cause": "Show the causal trigger.",
                    "protagonist_action": "Show the protagonist's consequential response.",
                    "escalation": "Raise the cost and narrow the options." if name in {"disaster_2", "disaster_3"} else "",
                }
                for name in ("setup", "disaster_1", "disaster_2", "disaster_3", "ending")
            },
            ensure_ascii=False,
            indent=2,
        )
    if step_number == 3:
        return json.dumps(
            {"characters": [{
                "name": "Protagonist", "role": "protagonist",
                "one_sentence_summary": single_line(source),
                "motivation": "Define the internal motivation.",
                "goal": "Define the external story goal.",
                "conflict": "Define the central opposition.",
                "epiphany": "Define the final realization.",
                "viewpoint_summary": "Expand the story from this character's viewpoint.",
            }]},
            ensure_ascii=False,
            indent=2,
        )
    if step_number == 4:
        return json.dumps(
            {"paragraphs": [
                {"beat_id": beat, "text": f"Expand the {beat.replace('_', ' ')} while preserving causal continuity."}
                for beat in ("setup", "disaster_1", "disaster_2", "disaster_3", "ending")
            ]},
            ensure_ascii=False,
            indent=2,
        )
    if step_number == 5:
        return json.dumps(
            {"viewpoints": [{
                "character_name": "Protagonist", "character_ref": "protagonist",
                "viewpoint_story": single_line(source),
                "knows": [], "does_not_know": [], "misunderstands": [],
            }]},
            ensure_ascii=False,
            indent=2,
        )
    if step_number == 6:
        return json.dumps(
            {"blocks": [{
                "record_id": "act-1-sequence-1", "act": "Act I", "section": "Opening",
                "sequence": 1, "synopsis": single_line(source),
                "step4_paragraph_refs": ["setup"], "character_refs": ["protagonist"],
            }]},
            ensure_ascii=False,
            indent=2,
        )
    if step_number == 8:
        return "\n".join(
            [
                "Scene 1",
                "- POV: TBD",
                f"- Goal: {single_line(source)}",
                "- Conflict: Define the immediate opposition.",
                "- Turning point: Define the irreversible change.",
                "- Outcome: Define the disaster, setback, or decisive result.",
                "- Required Canon: Link confirmed entities before drafting.",
                "- Forbidden facts: List information that cannot be revealed yet.",
                "- Information Delta: State what the reader and POV character learn.",
                "- Character State Delta: State how the POV character changes.",
                "- StoryThread Actions: plant: Define a reviewable narrative thread.",
                "- Open threads: List questions this scene opens or advances.",
            ]
        )
    return (
        "Use this as a structured development draft. Expand it into the requested "
        f"Snowflake artifact while preserving the project premise: {single_line(source)}"
    )


def draft_record_for_step(
    step_number: int, premise: str, user_input: str
) -> tuple[str, dict]:
    source = single_line(user_input or premise)
    if step_number == 6:
        return "act-1-sequence-1", {
            "record_id": "act-1-sequence-1",
            "act": "Act I",
            "section": "Opening",
            "sequence": 1,
            "synopsis": source,
            "step4_paragraph_refs": ["setup"],
            "character_refs": ["protagonist"],
        }
    if step_number == 7:
        return "character-protagonist", {
            "record_type": "character",
            "name": "Protagonist",
            "role": "protagonist",
            "one_sentence_summary": source,
            "motivation": "Define the internal motivation.",
            "goal": "Define the external goal.",
            "conflict": "Define the central opposition.",
            "epiphany": "Define the final realization.",
            "viewpoint_summary": source,
            "confirmed_facts": [],
        }
    if step_number == 8:
        return "scene-1", {
            "title": "Opening",
            "pov": "Protagonist",
            "goal": source,
            "conflict": "Define the immediate opposition.",
            "turning_point": "Define the irreversible change.",
            "outcome": "Define the decisive result.",
            "required_canon_ids": [],
            "forbidden_facts": [],
            "information_delta": "State what the reader and POV character learn.",
            "character_state_delta": "State how the POV character changes.",
            "story_thread_actions": [],
        }
    return "scene-1-expansion", {
        "scene_id": "scene-1",
        "beats": [source],
        "emotional_change": "Define the scene's emotional transition.",
        "chapter_plan": "Place the scene in the appropriate chapter after review.",
    }


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
