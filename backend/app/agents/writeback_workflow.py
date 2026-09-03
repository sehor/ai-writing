import json
from typing import Any

from app.agents.deepseek_workflow import DeepSeekSettings
from app.models import (
    CanonEntity,
    CanonEntityCreate,
    MemoryRecord,
    MemoryRecordCreate,
    ManuscriptRevision,
    NarrativeRelationCreate,
    StoryThreadCreate,
    StoryThreadEventCreate,
    StoryThreadStatusUpdate,
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
    if proposal.target == "canon_entity":
        if proposal.action == "update":
            validate_update_proposal(proposal)
        else:
            CanonEntityCreate.model_validate(proposal.payload)
        return
    if proposal.target == "memory_record":
        if proposal.action != "create":
            raise ValueError("Memory write-back proposals only support create actions.")
        MemoryRecordCreate.model_validate(proposal.payload)
        return
    if proposal.target == "narrative_relation":
        if proposal.action != "create":
            raise ValueError("Narrative relation proposals only support create actions.")
        allowed_fields = {
            "source",
            "target",
            "relation",
            "valid_from",
            "valid_to",
            "confidence",
            "source_ref",
            "status",
            "evidence",
        }
        unknown_fields = set(proposal.payload) - allowed_fields
        if unknown_fields:
            raise ValueError(
                "Narrative relation proposal contains unsupported fields: "
                + ", ".join(sorted(unknown_fields))
            )
        payload = {key: value for key, value in proposal.payload.items() if key != "evidence"}
        NarrativeRelationCreate.model_validate(payload)
        _validate_clp_evidence(proposal)
        return
    if proposal.target == "story_thread_status":
        if proposal.action != "update":
            raise ValueError("Story thread lifecycle proposals must use update actions.")
        subject_id = str(proposal.payload.get("subject_id", "")).strip()
        from_state = str(proposal.payload.get("from_state", "")).strip()
        proposed_state = str(proposal.payload.get("proposed_state", "")).strip()
        if not subject_id or subject_id != proposal.target_record_id:
            raise ValueError("Story thread lifecycle proposal target identity is invalid.")
        StoryThreadStatusUpdate.model_validate({"status": from_state})
        StoryThreadStatusUpdate.model_validate({"status": proposed_state})
        if from_state == proposed_state:
            raise ValueError("Story thread lifecycle proposal must change status.")
        _validate_clp_evidence(proposal)
        return
    if proposal.target == "story_thread":
        if proposal.action != "create":
            raise ValueError("Story thread proposals only support create actions.")
        StoryThreadCreate.model_validate(proposal.payload)
        return
    if proposal.target == "story_thread_event":
        if proposal.action != "create":
            raise ValueError("Story thread event proposals only support create actions.")
        event_payload = {
            key: value
            for key, value in proposal.payload.items()
            if key not in {"thread_title", "scene_proposal_id"}
        }
        StoryThreadEventCreate.model_validate(event_payload)
        if not proposal.target_record_id and not str(proposal.payload.get("thread_title", "")).strip():
            raise ValueError("Story thread event proposals require a thread id or title.")
        return
    raise ValueError(f"Unsupported write-back target: {proposal.target}")


def _validate_clp_evidence(proposal: WritebackProposalCreate) -> None:
    payload_source = str(proposal.payload.get("source_ref", "")).strip()
    if not proposal.source_ref or payload_source != proposal.source_ref:
        raise ValueError("CLP proposal source_ref must match its candidate payload.")
    evidence = proposal.payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("CLP proposals require traceable evidence.")
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("CLP proposal evidence must be structured objects.")
        if str(item.get("source_ref", "")).strip() != proposal.source_ref:
            raise ValueError("CLP proposal evidence must reference the accepted revision.")
        excerpt = str(item.get("excerpt", "")).strip()
        if not excerpt or len(excerpt) > 2000:
            raise ValueError("CLP proposal evidence excerpt is invalid.")


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
