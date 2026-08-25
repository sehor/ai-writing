import json
from typing import Any

from app.agents.deepseek_workflow import DeepSeekSettings
from app.models import (
    CanonEntity,
    CanonEntityCreate,
    MemoryRecord,
    MemoryRecordCreate,
    ManuscriptRevision,
    WritebackProposalCreate,
)
from app.review.writeback_apply import validate_update_proposal


def build_provider_writeback_proposals(
    settings: DeepSeekSettings,
    revision: ManuscriptRevision,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
) -> list[WritebackProposalCreate]:
    from app.agents.client_factory import get_openai_client

    client = get_openai_client(api_key=settings.api_key, base_url=settings.base_url)
    response = client.chat.completions.create(
        model=settings.model,
        messages=build_provider_messages(revision, canon_entities, memory_records),
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
    content = response.choices[0].message.content if response.choices else ""
    if not content:
        raise ValueError("empty provider response")
    payload = parse_provider_json(content)
    if not isinstance(payload, list):
        raise ValueError("response must be a JSON array")
    proposals = [WritebackProposalCreate.model_validate(item) for item in payload]
    for proposal in proposals:
        validate_writeback_payload(proposal)
    return proposals


def validate_writeback_payload(proposal: WritebackProposalCreate) -> None:
    """Structural validation before a proposal is persisted (P1-03).

    Create proposals carry their record shape in ``payload``; update
    proposals target an existing canon record by id with field-level
    changes. Anything malformed raises ValueError, which creation routes
    map to HTTP 422.
    """
    if proposal.action == "update":
        validate_update_proposal(proposal)
        return
    if proposal.target == "canon_entity":
        CanonEntityCreate.model_validate(proposal.payload)
        return
    MemoryRecordCreate.model_validate(proposal.payload)


def build_provider_messages(
    revision: ManuscriptRevision,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You propose structured write-back changes for AI Writing Studio. "
                "Return JSON only. Do not include Markdown. "
                "Every item must match one of these shapes: "
                "create: {target: 'canon_entity'|'memory_record', action: 'create', "
                "title: string, rationale: string, source_ref: string, payload: object}; "
                "update: {target: 'canon_entity', action: 'update', title: string, "
                "rationale: string, source_ref: string, target_record_id: string, "
                "expected_version: number, changes: {field: {before: string, after: string}}}. "
                "Create canon payloads must match CanonEntityCreate; memory payloads must "
                "match MemoryRecordCreate. Update 'field' must be one of entity_type, name, "
                "summary, current_state, constraints, last_seen, timeline_notes, and "
                "'expected_version' must be the current version of that canon record. "
                "Only propose facts that are strongly supported by the accepted manuscript "
                "revision. When unsure, omit the proposal."
            ),
        },
        {
            "role": "user",
            "content": build_provider_context(revision, canon_entities, memory_records),
        },
    ]


def build_provider_context(
    revision: ManuscriptRevision,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
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
    return "\n".join(
        [
            f"Source ref: manuscript_revision:{revision.id}",
            f"Scene id: {revision.scene_id}",
            f"Title: {revision.title}",
            f"Version: {revision.version}",
            "",
            "Existing Canon:",
            existing_canon,
            "",
            "Existing Memory:",
            existing_memory,
            "",
            "Accepted manuscript revision:",
            revision.content,
        ]
    )


def parse_provider_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def truncate_state(value: str, limit: int = 160) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text or "(empty)"
    return f"{text[: limit - 3]}..."
