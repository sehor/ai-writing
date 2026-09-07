import json
from dataclasses import dataclass
from typing import Any

from app.llm.gateway import ModelGateway, ModelRequest
from app.llm.policy import generation_policy_for
from app.llm.runtime import ModelExecution, ModelRuntime, as_model_runtime
from app.models import (
    CanonEntity,
    CanonEntityCreate,
    MemoryRecord,
    MemoryRecordCreate,
    ManuscriptRevision,
    ModelExecutionOptions,
    NarrativeRelationCreate,
    StoryThreadCreate,
    StoryThreadEventCreate,
    StoryThreadStatusUpdate,
    WritebackProposalCreate,
)
from app.review.writeback_apply import validate_update_proposal
from app.prompts import compile_writeback_prompt


@dataclass(frozen=True, slots=True)
class GeneratedWritebackProposals:
    proposals: list[WritebackProposalCreate]
    execution: ModelExecution

    @property
    def completion(self):
        return self.execution.completion


def generate_gateway_writeback_proposals(
    runtime: ModelRuntime | ModelGateway,
    revision: ManuscriptRevision,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
    *,
    project_id: str = "",
    options: ModelExecutionOptions | None = None,
) -> GeneratedWritebackProposals:
    prompt = compile_writeback_prompt(revision, canon_entities, memory_records)
    request = ModelRequest(
        prompt=prompt,
        policy=generation_policy_for(prompt),
        metadata={"project_id": project_id},
    )
    execution = as_model_runtime(runtime).execute(
        request, options, validate_content=parse_writeback_proposals
    )
    proposals = execution.validated_value
    return GeneratedWritebackProposals(proposals=proposals, execution=execution)


def parse_writeback_proposals(content: str) -> list[WritebackProposalCreate]:
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
        if (
            not proposal.target_record_id
            and not str(proposal.payload.get("thread_title", "")).strip()
        ):
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
