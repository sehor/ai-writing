"""Versioned Snowflake prompt compilation without provider dependencies."""

import json
from typing import Protocol

from app.llm_wiki.interfaces import WikiContextResult
from app.models import (
    CanonEntity,
    MemoryRecord,
    ProjectSummary,
    SnowflakeArtifact,
    SnowflakeGenerationRequest,
    SnowflakeRecordRevision,
    SnowflakeStep,
)
from app.prompts.models import PromptMessage, PromptPlan, ResponseContract
from app.prompts.manager import PromptManager, default_prompt_manager
from app.prompts.registry import PromptDefinition, PromptRegistry, default_prompt_registry
from app.snowflake.contracts import (
    CharacterBibleRecord,
    RECORD_CONTRACTS,
    STEP_CONTRACTS,
)
from app.text_utils import truncate as truncate_context


class SnowflakePromptState(Protocol):
    request: SnowflakeGenerationRequest
    project: ProjectSummary | None
    step: SnowflakeStep | None
    previous_artifacts: list[SnowflakeArtifact]
    previous_records: dict[int, list[SnowflakeRecordRevision]]
    canon_entities: list[CanonEntity]
    memory_records: list[MemoryRecord]
    llm_wiki_context: WikiContextResult | None


def prompt_id_for_step(step_number: int) -> str:
    if not 1 <= step_number <= 10:
        raise ValueError(f"Unsupported Snowflake step: {step_number}")
    if step_number == 10:
        return "snowflake.step10.scene"
    return f"snowflake.step{step_number:02d}"


def method_asset_id_for_step(step_number: int) -> str:
    if not 1 <= step_number <= 10:
        raise ValueError(f"Unsupported Snowflake step: {step_number}")
    return f"snowflake.step{step_number:02d}.method"


def response_contract_for_step(step_number: int) -> ResponseContract:
    schema_name = f"snowflake.step{step_number:02d}.v2"
    if step_number in {6, 7, 8, 9}:
        if step_number == 7:
            payload_schema: dict = CharacterBibleRecord.model_json_schema()
        else:
            record_contract = RECORD_CONTRACTS[step_number]
            payload_schema = record_contract.model_json_schema()
        return ResponseContract(
            media_type="application/json",
            schema_name=schema_name,
            schema_version="2",
            json_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["records"],
                "properties": {
                    "records": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["record_id", "payload"],
                            "properties": {
                                "record_id": {"type": "string", "minLength": 1},
                                "payload": payload_schema,
                            },
                        },
                    }
                },
            },
        )
    contract = STEP_CONTRACTS.get(step_number)
    if contract is not None:
        return ResponseContract(
            media_type="application/json",
            schema_name=schema_name,
            schema_version="2",
            json_schema=contract.model_json_schema(),
        )
    return ResponseContract(
        media_type="text/markdown",
        schema_name=schema_name,
        schema_version="2",
    )


def register_snowflake_prompts(
    registry: PromptRegistry,
    manager: PromptManager = default_prompt_manager,
) -> None:
    for step_number in range(1, 11):
        prompt_id = prompt_id_for_step(step_number)
        registry.register(
            PromptDefinition(
                prompt_id=prompt_id,
                version=manager.version(method_asset_id_for_step(step_number)),
                use_case="snowflake_generation" if step_number < 10 else "manuscript_scene",
                response_contract=response_contract_for_step(step_number),
            )
        )


def compile_snowflake_prompt(
    state: SnowflakePromptState,
    registry: PromptRegistry = default_prompt_registry,
    manager: PromptManager = default_prompt_manager,
) -> PromptPlan:
    definition = registry.get(prompt_id_for_step(state.request.step_number))
    return PromptPlan(
        prompt_id=definition.prompt_id,
        prompt_version=definition.version,
        use_case=definition.use_case,
        messages=(
            PromptMessage(role="system", content=manager.render("snowflake.system")),
            PromptMessage(role="user", content=build_stable_context_prefix(state, manager)),
            PromptMessage(role="user", content=build_generation_instruction(state, manager)),
        ),
        response_contract=definition.response_contract,
        metadata={"step_number": str(state.request.step_number)},
    )


def build_stable_context_prefix(
    state: SnowflakePromptState,
    manager: PromptManager = default_prompt_manager,
) -> str:
    project_title = state.project.title if state.project else state.request.project_id
    premise = state.project.premise if state.project else ""
    step_title = state.step.title if state.step else f"Step {state.request.step_number}"
    step_artifact = state.step.artifact if state.step else "artifact"
    step_description = state.step.description if state.step else ""
    return manager.render(
        "snowflake.context",
        {
            "project_title": project_title,
            "premise": premise or "No premise recorded.",
            "step_number": state.request.step_number,
            "step_title": step_title,
            "step_artifact": step_artifact,
            "step_description": step_description,
            "previous_context": format_previous_context(state),
            "canon_context": format_canon_entities(state.canon_entities),
            "memory_context": format_memory_records(state.memory_records),
            "wiki_context": format_llm_wiki_context(state),
        },
    )


def build_generation_instruction(
    state: SnowflakePromptState,
    manager: PromptManager = default_prompt_manager,
) -> str:
    step_title = state.step.title if state.step else f"Step {state.request.step_number}"
    record_selection_rules = ""
    if state.request.step_number in {6, 7, 8, 9}:
        if state.request.step_number == 7:
            record_schemas = [CharacterBibleRecord.model_json_schema()]
        else:
            record_schemas = [RECORD_CONTRACTS[state.request.step_number].model_json_schema()]
        if state.request.target_records:
            record_selection_rules = manager.render(
                "snowflake.records.selection.selected",
                {"target_records": json.dumps(state.request.target_records, ensure_ascii=False)},
            )
        else:
            record_selection_rules = manager.render("snowflake.records.selection.new")
        output_contract_rules = manager.render(
            "snowflake.output.records",
            {"record_schemas": json.dumps(record_schemas, ensure_ascii=False)},
        )
    else:
        contract = STEP_CONTRACTS.get(state.request.step_number)
        if contract is not None:
            output_contract_rules = manager.render(
                "snowflake.output.json",
                {"response_schema": json.dumps(contract.model_json_schema(), ensure_ascii=False)},
            )
        else:
            output_contract_rules = manager.render(
                "snowflake.output.markdown", {"step_title": step_title}
            )
    request = manager.render(
        "snowflake.request",
        {
            "author_direction": state.request.user_input,
            "generation_mode": state.request.generation_mode,
            "base_revision": state.request.base_revision_id or "none",
            "record_selection_rules": record_selection_rules,
            "output_contract_rules": output_contract_rules,
        },
    )
    return "\n\n".join(
        (
            manager.render(method_asset_id_for_step(state.request.step_number)),
            request,
        )
    )


def format_previous_artifacts(artifacts: list[SnowflakeArtifact], max_chars: int) -> str:
    if not artifacts:
        return "No previous artifacts saved."
    context = "\n\n".join(
        f"### Step {item.step_number}: {item.artifact}\n{item.content}"
        for item in sorted(artifacts, key=lambda item: item.step_number, reverse=True)
    )
    return truncate_context(context, max_chars)


def select_relevant_upstream_records(state: SnowflakePromptState) -> list[SnowflakeRecordRevision]:
    """Rank accepted upstream records against the instruction and selected records."""
    query_source = "\n".join(
        [
            state.request.user_input,
            json.dumps(state.request.target_records, ensure_ascii=False),
        ]
    )
    query_tokens = _search_tokens(query_source)
    explicit_refs = _scalar_references(state.request.target_records)
    ranked: list[tuple[int, int, int, str, SnowflakeRecordRevision]] = []
    for step_number, records in state.previous_records.items():
        for record in records:
            searchable = f"{record.record_id} {json.dumps(record.payload, ensure_ascii=False)}"
            overlap = len(query_tokens & _search_tokens(searchable))
            explicit = 1 if record.record_id.lower() in explicit_refs else 0
            ranked.append((explicit, overlap, step_number, record.record_id, record))
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    return [item[-1] for item in ranked]


def _search_tokens(value: str) -> set[str]:
    normalized = "".join(character.lower() if character.isalnum() else " " for character in value)
    return {token for token in normalized.split() if len(token) >= 3}


def _scalar_references(value) -> set[str]:
    if isinstance(value, dict):
        return {item for child in value.values() for item in _scalar_references(child)}
    if isinstance(value, list):
        return {item for child in value for item in _scalar_references(child)}
    return {str(value).strip().lower()} if value not in {None, ""} else set()


def format_previous_context(state: SnowflakePromptState) -> str:
    max_chars = state.request.previous_artifacts_context_chars
    records = select_relevant_upstream_records(state)
    if not records:
        return format_previous_artifacts(state.previous_artifacts, max_chars)
    record_budget = max(1000, int(max_chars * 0.7))
    record_context = format_previous_records(records, record_budget)
    artifact_budget = max(0, max_chars - len(record_context) - 2)
    artifact_context = (
        format_previous_artifacts(state.previous_artifacts, artifact_budget)
        if artifact_budget >= 100
        else ""
    )
    return "\n\n".join(part for part in (record_context, artifact_context) if part)


def format_previous_records(records: list[SnowflakeRecordRevision], max_chars: int) -> str:
    if not records:
        return "No accepted upstream records."
    context = "\n\n".join(
        "\n".join(
            [
                f"### Step {record.step_number} record: {record.record_id}",
                json.dumps(record.payload, ensure_ascii=False, sort_keys=True),
            ]
        )
        for record in records
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


def format_llm_wiki_context(state: SnowflakePromptState) -> str:
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
