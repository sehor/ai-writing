from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain_models.writeback import WritebackProposal, WritebackProposalCreate

HermesProcessStatus = Literal["completed", "partial", "failed"]


HermesWikiChangeAction = Literal["created", "updated", "skipped"]


HermesIssueSeverity = Literal["info", "warning", "error"]


class WikiExportFile(BaseModel):
    path: str
    content_type: str
    content: str


class WikiExportResponse(BaseModel):
    project_id: str
    title: str
    file_count: int
    generated_at: str
    files: list[WikiExportFile] = Field(default_factory=list)


class HermesWikiChange(BaseModel):
    path: str
    action: HermesWikiChangeAction
    reason: str = ""


class HermesProcessingIssue(BaseModel):
    severity: HermesIssueSeverity
    code: str
    message: str
    source_ref: str = ""


class HermesRevisionProcessResult(BaseModel):
    status: HermesProcessStatus
    summary: str
    wiki_changes: list[HermesWikiChange] = Field(default_factory=list)
    issues: list[HermesProcessingIssue] = Field(default_factory=list)
    writeback_proposals: list[WritebackProposalCreate] = Field(default_factory=list)
    processed_source_ref: str


class HermesRevisionProcessResponse(BaseModel):
    status: HermesProcessStatus
    summary: str
    wiki_changes: list[HermesWikiChange] = Field(default_factory=list)
    issues: list[HermesProcessingIssue] = Field(default_factory=list)
    writeback_proposals: list[WritebackProposal] = Field(default_factory=list)
    processed_source_ref: str
    cached: bool = False
    analysis_run_id: str = ""
