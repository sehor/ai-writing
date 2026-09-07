"""Provider-neutral prompts for scene, reference, and write-back generation."""

import json

from app.models import CanonEntity, MemoryRecord, ManuscriptRevision, WritebackProposalCreate
from app.prompts.manager import PromptManager, default_prompt_manager
from app.prompts.models import PromptMessage, PromptPlan, ResponseContract
from app.prompts.registry import PromptDefinition, PromptRegistry, default_prompt_registry
from app.snowflake.contracts import STEP_CONTRACTS


def register_creative_prompts(
    registry: PromptRegistry,
    manager: PromptManager = default_prompt_manager,
) -> None:
    writeback_item_schema = WritebackProposalCreate.model_json_schema()
    writeback_definitions = writeback_item_schema.pop("$defs", {})
    registry.register(
        PromptDefinition(
            prompt_id="reference.suggestion",
            version=manager.version("creative.reference.system"),
            use_case="reference_suggestion",
            response_contract=ResponseContract(
                media_type="text/markdown",
                schema_name="reference.suggestion.v1",
                schema_version="1",
            ),
        )
    )
    registry.register(
        PromptDefinition(
            prompt_id="system.response-repair",
            version=manager.version("creative.repair.system"),
            use_case="response_repair",
            response_contract=ResponseContract(
                media_type="application/json",
                schema_name="response.repair.v1",
                schema_version="1",
            ),
        )
    )
    registry.register(
        PromptDefinition(
            prompt_id="writeback.propose",
            version=manager.version("creative.writeback.system"),
            use_case="writeback_proposal",
            response_contract=ResponseContract(
                media_type="application/json",
                schema_name="writeback.proposal-list.v1",
                schema_version="1",
                json_schema={
                    "type": "array",
                    "items": writeback_item_schema,
                    "$defs": writeback_definitions,
                },
            ),
        )
    )


def compile_manuscript_prompt(
    context: str,
    registry: PromptRegistry = default_prompt_registry,
    manager: PromptManager = default_prompt_manager,
) -> PromptPlan:
    definition = registry.get("snowflake.step10.scene")
    return PromptPlan(
        prompt_id=definition.prompt_id,
        prompt_version=definition.version,
        use_case=definition.use_case,
        messages=(
            PromptMessage(role="system", content=manager.render("snowflake.system")),
            PromptMessage(
                role="user",
                content="\n\n".join(
                    (
                        manager.render("snowflake.step10.method"),
                        manager.render("creative.manuscript.context", {"context": context}),
                        manager.render(
                            "snowflake.output.json",
                            {
                                "response_schema": json.dumps(
                                    STEP_CONTRACTS[10].model_json_schema(), ensure_ascii=False
                                )
                            },
                        ),
                    )
                ),
            ),
        ),
        response_contract=definition.response_contract,
    )


def compile_reference_prompt(
    context: str,
    registry: PromptRegistry = default_prompt_registry,
    manager: PromptManager = default_prompt_manager,
) -> PromptPlan:
    definition = registry.get("reference.suggestion")
    return PromptPlan(
        prompt_id=definition.prompt_id,
        prompt_version=definition.version,
        use_case=definition.use_case,
        messages=(
            PromptMessage(role="system", content=manager.render("creative.reference.system")),
            PromptMessage(
                role="user",
                content=manager.render("creative.reference.request", {"context": context}),
            ),
        ),
        response_contract=definition.response_contract,
    )


def compile_writeback_prompt(
    revision: ManuscriptRevision,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
    registry: PromptRegistry = default_prompt_registry,
    manager: PromptManager = default_prompt_manager,
) -> PromptPlan:
    definition = registry.get("writeback.propose")
    return PromptPlan(
        prompt_id=definition.prompt_id,
        prompt_version=definition.version,
        use_case=definition.use_case,
        messages=(
            PromptMessage(role="system", content=manager.render("creative.writeback.system")),
            PromptMessage(
                role="user",
                content=build_writeback_context(revision, canon_entities, memory_records, manager),
            ),
        ),
        response_contract=definition.response_contract,
    )


def compile_repair_prompt(
    original: PromptPlan,
    invalid_content: str,
    validation_error: str,
    registry: PromptRegistry = default_prompt_registry,
    manager: PromptManager = default_prompt_manager,
) -> PromptPlan:
    definition = registry.get("system.response-repair")
    contract = original.response_contract
    schema = (
        json.dumps(contract.json_schema, ensure_ascii=False, sort_keys=True)
        if contract.json_schema is not None
        else f"media_type={contract.media_type}, schema={contract.schema_name}"
    )
    original_messages = "\n\n".join(
        f"[{message.role}]\n{message.content}" for message in original.messages
    )
    return PromptPlan(
        prompt_id=definition.prompt_id,
        prompt_version=definition.version,
        use_case=definition.use_case,
        messages=(
            PromptMessage(
                role="system",
                content=manager.render("creative.repair.system"),
            ),
            PromptMessage(
                role="user",
                content=manager.render(
                    "creative.repair.request",
                    {
                        "original_prompt_id": original.prompt_id,
                        "original_prompt_version": original.prompt_version,
                        "schema_name": contract.schema_name,
                        "schema_version": contract.schema_version,
                        "schema": schema[:20_000],
                        "original_messages": original_messages[:60_000],
                        "validation_error": validation_error[:1_000],
                        "invalid_content": invalid_content[:20_000],
                    },
                ),
            ),
        ),
        response_contract=contract,
        metadata={"repairs_prompt_id": original.prompt_id},
    )


def build_writeback_context(
    revision: ManuscriptRevision,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
    manager: PromptManager = default_prompt_manager,
) -> str:
    existing_canon = (
        "\n".join(
            f"- id={entity.id} v{entity.version} | {entity.entity_type}: {entity.name} | "
            f"state: {truncate_state(entity.current_state)}"
            for entity in canon_entities[:40]
        )
        or "No Canon entities recorded."
    )
    existing_memory = (
        "\n".join(f"- {record.record_type}: {record.title}" for record in memory_records[:40])
        or "No Memory records recorded."
    )
    return manager.render(
        "creative.writeback.request",
        {
            "revision_id": revision.id,
            "scene_id": revision.scene_id,
            "title": revision.title,
            "revision_version": revision.version,
            "existing_canon": existing_canon,
            "existing_memory": existing_memory,
            "revision_content": revision.content,
        },
    )


def truncate_state(value: str, limit: int = 160) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text or "(empty)"
    return f"{text[: limit - 3]}..."
