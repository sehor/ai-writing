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
