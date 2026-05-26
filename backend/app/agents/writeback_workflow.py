import json
from typing import Any

from app.agents.deepseek_workflow import DeepSeekSettings
from app.agents.writing_workflow import WorkflowNotConfiguredError
from app.models import (
    CanonEntity,
    CanonEntityCreate,
    MemoryRecord,
    MemoryRecordCreate,
    ManuscriptRevision,
    WritebackProposalCreate,
)


def build_provider_writeback_proposals(
    settings: DeepSeekSettings,
    revision: ManuscriptRevision,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
) -> list[WritebackProposalCreate]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise WorkflowNotConfiguredError(
            "The OpenAI-compatible SDK is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc

    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
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
                "Every item must match this shape: "
                "{target: 'canon_entity'|'memory_record', action: 'create', title: string, "
                "rationale: string, source_ref: string, payload: object}. "
                "Canon payload must match CanonEntityCreate. Memory payload must match MemoryRecordCreate. "
                "Only propose facts that are strongly supported by the accepted manuscript revision. "
                "When unsure, omit the proposal."
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
    existing_canon = "\n".join(
        f"- {entity.entity_type}: {entity.name}"
        for entity in canon_entities[:40]
    ) or "No Canon entities recorded."
    existing_memory = "\n".join(
        f"- {record.record_type}: {record.title}"
        for record in memory_records[:40]
    ) or "No Memory records recorded."
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
