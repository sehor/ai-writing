from typing import Literal, Protocol, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import (
    ManuscriptRevision,
    NarrativeRelation,
    StoryThread,
    StoryThreadStatus,
    WritebackProposalCreate,
)

NARRATIVE_CLP_PROFILE_NAME = "ai-writing-narrative"
NARRATIVE_CLP_PROFILE_VERSION = "1"

NARRATIVE_CLP_ENTITY_TYPES = (
    "Character",
    "Location",
    "Item",
    "Event",
    "StoryFact",
    "StoryThread",
    "Secret",
    "Scene",
    "Arc",
)
NARRATIVE_CLP_CANDIDATE_ENTITY_TYPES = ("Character", "Location", "Item")
NARRATIVE_CLP_RELATION_TYPES = (
    "CAUSES",
    "CHANGES_STATE",
    "KNOWS",
    "HIDES_FROM",
    "LOVES",
    "HATES",
    "OWES",
    "SUSPECTS",
    "PLANTED_AT",
    "REINFORCED_AT",
    "MISDIRECTED_AT",
    "PAYS_OFF_AT",
    "REFERENCES",
    "CONTRADICTS",
)

CandidateEntityType = Literal["Character", "Location", "Item"]
CandidateRelationType = Literal[
    "CAUSES",
    "CHANGES_STATE",
    "KNOWS",
    "HIDES_FROM",
    "LOVES",
    "HATES",
    "OWES",
    "SUSPECTS",
    "PLANTED_AT",
    "REINFORCED_AT",
    "MISDIRECTED_AT",
    "PAYS_OFF_AT",
    "REFERENCES",
    "CONTRADICTS",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompilerEvidence(_StrictModel):
    source_ref: str = Field(min_length=1, max_length=240)
    excerpt: str = Field(min_length=1, max_length=2000)

    @field_validator("source_ref", "excerpt")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class CandidateEntity(_StrictModel):
    entity_type: CandidateEntityType
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=1000)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str = Field(min_length=1, max_length=240)
    evidence: list[CompilerEvidence] = Field(min_length=1, max_length=20)

    @field_validator("name", "summary", "source_ref")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class CandidateRelation(_StrictModel):
    source: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=240)
    relation: CandidateRelationType
    valid_from: int = Field(ge=0, le=999)
    valid_to: int | None = Field(default=None, ge=0, le=999)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str = Field(min_length=1, max_length=240)
    evidence: list[CompilerEvidence] = Field(min_length=1, max_length=20)

    @field_validator("source", "target", "source_ref")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_temporal_range(self) -> "CandidateRelation":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to cannot be before valid_from")
        return self


class CandidateLifecycleChange(_StrictModel):
    subject_type: Literal["StoryThread"] = "StoryThread"
    subject_id: str = Field(min_length=1, max_length=160)
    from_state: StoryThreadStatus
    proposed_state: StoryThreadStatus
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str = Field(min_length=1, max_length=240)
    evidence: list[CompilerEvidence] = Field(min_length=1, max_length=20)

    @field_validator("subject_id", "source_ref")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_change(self) -> "CandidateLifecycleChange":
        if self.from_state == self.proposed_state:
            raise ValueError("lifecycle candidate must propose a different state")
        return self


class CompilerContextEntity(_StrictModel):
    id: str = Field(min_length=1, max_length=160)
    entity_type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)


class CompilerContextThread(_StrictModel):
    id: str = Field(min_length=1, max_length=160)
    thread_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=240)
    status: StoryThreadStatus


class CompilerContextRelation(_StrictModel):
    id: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=240)
    target: str = Field(min_length=1, max_length=240)
    relation: str = Field(min_length=1, max_length=160)
    valid_from: int = Field(ge=0, le=999)
    valid_to: int | None = Field(default=None, ge=0, le=999)
    confidence: float = Field(ge=0.0, le=1.0)
    source_ref: str = Field(default="", max_length=240)


class KnowledgeCompilerContext(_StrictModel):
    entities: list[CompilerContextEntity] = Field(default_factory=list, max_length=200)
    story_threads: list[CompilerContextThread] = Field(default_factory=list, max_length=200)
    relations: list[CompilerContextRelation] = Field(default_factory=list, max_length=500)


class KnowledgeCompilerSchema(_StrictModel):
    entity_types: list[str]
    candidate_entity_types: list[str]
    relation_types: list[str]
    story_thread_statuses: list[str]


class KnowledgeCompilerRequest(_StrictModel):
    project_id: str = Field(min_length=1, max_length=120)
    revision_id: str = Field(min_length=1, max_length=160)
    scene_id: str = Field(min_length=1, max_length=160)
    scene_sequence: int = Field(ge=1, le=999)
    source_ref: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=160)
    revision_text: str = Field(min_length=1, max_length=40000)
    revision_version: int = Field(ge=1)
    profile_name: str = Field(min_length=1, max_length=120)
    profile_version: str = Field(min_length=1, max_length=80)
    compiler_version: str = Field(min_length=1, max_length=120)
    context: KnowledgeCompilerContext
    domain_schema: KnowledgeCompilerSchema


class KnowledgeCompilerResult(_StrictModel):
    project_id: str = Field(min_length=1, max_length=120)
    revision_id: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(min_length=1, max_length=240)
    profile_name: str = Field(min_length=1, max_length=120)
    profile_version: str = Field(min_length=1, max_length=80)
    compiler_version: str = Field(min_length=1, max_length=120)
    entity_candidates: list[CandidateEntity] = Field(default_factory=list, max_length=200)
    relation_candidates: list[CandidateRelation] = Field(default_factory=list, max_length=500)
    lifecycle_candidates: list[CandidateLifecycleChange] = Field(
        default_factory=list, max_length=200
    )


class KnowledgeCompiler(Protocol):
    compiler_version: str

    def extract_revision(self, request: KnowledgeCompilerRequest) -> KnowledgeCompilerResult: ...


class DisabledKnowledgeCompiler:
    """No-op compiler used when no local CLP bridge is configured.

    The post-accept job still records a successful derived run with zero
    candidates, while explicitly configured sidecars retain normal failure
    and retry semantics.
    """

    compiler_version = "disabled"

    def extract_revision(self, request: KnowledgeCompilerRequest) -> KnowledgeCompilerResult:
        return KnowledgeCompilerResult(
            project_id=request.project_id,
            revision_id=request.revision_id,
            source_ref=request.source_ref,
            profile_name=request.profile_name,
            profile_version=request.profile_version,
            compiler_version=request.compiler_version,
        )


def build_revision_compiler_request(
    *,
    revision: ManuscriptRevision,
    scene_sequence: int,
    canon_entities: list,
    story_threads: list[StoryThread],
    narrative_relations: list[NarrativeRelation],
    compiler_version: str,
) -> KnowledgeCompilerRequest:
    return KnowledgeCompilerRequest(
        project_id=revision.project_id,
        revision_id=revision.id,
        scene_id=revision.scene_id,
        scene_sequence=scene_sequence,
        source_ref=f"manuscript_revision:{revision.id}",
        title=revision.title,
        revision_text=revision.content,
        revision_version=revision.version,
        profile_name=NARRATIVE_CLP_PROFILE_NAME,
        profile_version=NARRATIVE_CLP_PROFILE_VERSION,
        compiler_version=compiler_version,
        context=KnowledgeCompilerContext(
            entities=[
                CompilerContextEntity(
                    id=item.id,
                    entity_type=item.entity_type,
                    name=item.name,
                    version=item.version,
                )
                for item in canon_entities
            ],
            story_threads=[
                CompilerContextThread(
                    id=item.id,
                    thread_type=item.thread_type,
                    title=item.title,
                    status=item.status,
                )
                for item in story_threads
            ],
            relations=[
                CompilerContextRelation(
                    id=item.id,
                    source=item.source,
                    target=item.target,
                    relation=item.relation,
                    valid_from=item.valid_from,
                    valid_to=item.valid_to,
                    confidence=item.confidence,
                    source_ref=item.source_ref,
                )
                for item in narrative_relations
            ],
        ),
        domain_schema=KnowledgeCompilerSchema(
            entity_types=list(NARRATIVE_CLP_ENTITY_TYPES),
            candidate_entity_types=list(NARRATIVE_CLP_CANDIDATE_ENTITY_TYPES),
            relation_types=list(NARRATIVE_CLP_RELATION_TYPES),
            story_thread_statuses=list(get_args(StoryThreadStatus)),
        ),
    )


def _evidence_payload(candidate) -> list[dict]:
    return [item.model_dump(mode="json") for item in candidate.evidence]


def normalize_compiler_candidates(result: KnowledgeCompilerResult) -> list[WritebackProposalCreate]:
    proposals: list[WritebackProposalCreate] = []
    canon_type_by_candidate = {
        "Character": "character",
        "Location": "location",
        "Item": "item",
    }
    for candidate in result.entity_candidates:
        proposals.append(
            WritebackProposalCreate(
                target="canon_entity",
                action="create",
                title=f"CLP entity: {candidate.name}",
                rationale=(
                    f"CLP candidate ({candidate.entity_type}, confidence={candidate.confidence:.2f}). "
                    f"Evidence: {candidate.evidence[0].excerpt}"
                ),
                payload={
                    "entity_type": canon_type_by_candidate[candidate.entity_type],
                    "name": candidate.name,
                    "summary": candidate.summary,
                },
                source_ref=candidate.source_ref,
            )
        )
    for candidate in result.relation_candidates:
        proposals.append(
            WritebackProposalCreate(
                target="narrative_relation",
                action="create",
                title=f"CLP relation: {candidate.source} {candidate.relation} {candidate.target}",
                rationale=(
                    f"CLP relation candidate with confidence={candidate.confidence:.2f}; "
                    "acceptance is required before Narrative Domain writeback."
                ),
                payload={
                    "source": candidate.source,
                    "target": candidate.target,
                    "relation": candidate.relation,
                    "valid_from": candidate.valid_from,
                    "valid_to": candidate.valid_to,
                    "confidence": candidate.confidence,
                    "source_ref": candidate.source_ref,
                    "status": "confirmed",
                    "evidence": _evidence_payload(candidate),
                },
                source_ref=candidate.source_ref,
            )
        )
    for candidate in result.lifecycle_candidates:
        proposals.append(
            WritebackProposalCreate(
                target="story_thread_status",
                action="update",
                title=f"CLP lifecycle: {candidate.subject_id} → {candidate.proposed_state}",
                rationale=(
                    f"CLP lifecycle candidate with confidence={candidate.confidence:.2f}; "
                    "acceptance is required before StoryThread mutation."
                ),
                payload={
                    "subject_type": candidate.subject_type,
                    "subject_id": candidate.subject_id,
                    "from_state": candidate.from_state,
                    "proposed_state": candidate.proposed_state,
                    "confidence": candidate.confidence,
                    "source_ref": candidate.source_ref,
                    "evidence": _evidence_payload(candidate),
                },
                source_ref=candidate.source_ref,
                target_record_id=candidate.subject_id,
            )
        )
    return proposals
