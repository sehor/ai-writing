"""Analysis run records: idempotent, re-runnable derived analyses."""

from typing import Literal

from pydantic import BaseModel, Field

AnalysisProcessor = Literal[
    "local_writeback",
    "deepseek_writeback",
    "hermes",
    "consistency_checker",
]
AnalysisRunStatus = Literal["succeeded", "failed"]


class AnalysisRun(BaseModel):
    id: str
    project_id: str
    source_ref: str
    processor: str
    input_hash: str = Field(min_length=1)
    status: AnalysisRunStatus
    result_json: dict = Field(default_factory=dict)
    run_version: int = Field(default=1, ge=1)
    created_at: str
    completed_at: str = ""


FindingSeverity = Literal["info", "warning", "critical"]
FindingConfidence = Literal["exact", "heuristic"]


class ConsistencyFinding(BaseModel):
    """One evidence-backed consistency observation about a revision (P1-06)."""

    id: str
    severity: FindingSeverity
    rule_code: str
    title: str
    description: str
    manuscript_source_ref: str
    manuscript_excerpt: str
    canon_entity_id: str | None = None
    canon_field: str | None = None
    expected_value: str
    observed_value: str
    suggested_action: str
    confidence: FindingConfidence = "heuristic"


class ConsistencyReportSummary(BaseModel):
    finding_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0


class ConsistencyReport(BaseModel):
    project_id: str
    source_ref: str
    processor: str = "consistency_checker"
    cached: bool = False
    run_id: str = ""
    run_version: int = 1
    summary: ConsistencyReportSummary = Field(default_factory=ConsistencyReportSummary)
    findings: list[ConsistencyFinding] = Field(default_factory=list)


StyleDriftSeverity = Literal["info", "warning", "critical"]


class StyleProfile(BaseModel):
    project_id: str
    scope: str = "project"
    sample_count: int = 0
    character_count: int = 0
    metrics: dict[str, float] = Field(default_factory=dict)
    frequent_terms: list[str] = Field(default_factory=list)


class StyleDriftFinding(BaseModel):
    metric: str
    severity: StyleDriftSeverity
    baseline: float
    observed: float
    relative_change: float
    explanation: str


class StyleDriftReport(BaseModel):
    project_id: str
    source_ref: str
    profile_scope: str
    sample_count: int = 0
    findings: list[StyleDriftFinding] = Field(default_factory=list)
