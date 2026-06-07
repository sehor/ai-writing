from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator


WikiSourceKind = Literal["snowflake_artifact", "manuscript_revision"]
WikiKnowledgeClass = Literal["planned", "observed"]
WikiDocumentStatus = Literal["draft", "approved", "superseded"]
WikiInsightDisposition = Literal["advisory"]


class WikiSourceDocument(BaseModel):
    project_id: str = Field(min_length=1, max_length=160)
    source_kind: WikiSourceKind
    source_ref: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=200000)
    snowflake_step: int = Field(ge=1, le=10)
    artifact_type: str = Field(min_length=1, max_length=120)
    knowledge_class: WikiKnowledgeClass
    status: WikiDocumentStatus = "approved"
    version: int = Field(default=1, ge=1)
    supersedes: str = Field(default="", max_length=240)
    scope: str = Field(default="", max_length=240)
    story_position: int | None = Field(default=None, ge=0)

    @field_validator(
        "project_id",
        "source_ref",
        "title",
        "content",
        "artifact_type",
        "supersedes",
        "scope",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class WikiContextQuery(BaseModel):
    project_id: str = Field(min_length=1, max_length=160)
    snowflake_step: int = Field(ge=1, le=10)
    instruction: str = Field(default="", max_length=4000)
    scope: str = Field(default="", max_length=240)
    story_position: int | None = Field(default=None, ge=0)
    spoiler_horizon: int | None = Field(default=None, ge=0)

    @field_validator("project_id", "instruction", "scope")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class WikiEvidence(BaseModel):
    source_ref: str
    title: str
    excerpt: str
    knowledge_class: WikiKnowledgeClass
    snowflake_step: int = Field(ge=1, le=10)
    scope: str = ""
    story_position: int | None = None


class WikiConstraint(BaseModel):
    text: str
    source_refs: list[str] = Field(default_factory=list)


class WikiContextResult(BaseModel):
    summary: str
    evidence: list[WikiEvidence] = Field(default_factory=list)
    constraints: list[WikiConstraint] = Field(default_factory=list)


class WikiInsightQuery(WikiContextQuery):
    pass


class WikiInsight(BaseModel):
    kind: str
    summary: str
    detail: str
    source_refs: list[str] = Field(default_factory=list)
    disposition: WikiInsightDisposition = "advisory"


class WikiInsightResult(BaseModel):
    summary: str
    insights: list[WikiInsight] = Field(default_factory=list)


class WikiIngestionResult(BaseModel):
    status: Literal["stored", "updated", "skipped"]
    source_ref: str
    stored_path: str = ""
    superseded_source_ref: str = ""


class LlmWiki(Protocol):
    def ingest(self, document: WikiSourceDocument) -> WikiIngestionResult:
        pass

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        pass

    def analyze(self, query: WikiInsightQuery) -> WikiInsightResult:
        pass
