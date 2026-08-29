from typing import Literal

from pydantic import BaseModel, Field


OutboxJobType = Literal[
    "llm_wiki_ingest",
    "consistency_analysis",
    "writeback_analysis",
    "clp_extraction",
]
OutboxJobStatus = Literal["pending", "processing", "succeeded", "failed"]


class OutboxJob(BaseModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    job_type: OutboxJobType
    aggregate_type: str = Field(min_length=1)
    aggregate_id: str = Field(min_length=1)
    payload: dict = Field(default_factory=dict)
    status: OutboxJobStatus
    attempt_count: int = Field(default=0, ge=0)
    last_error: str = ""
    created_at: str = ""
    completed_at: str = ""
    processing_started_at: str = ""
