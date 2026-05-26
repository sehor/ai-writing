from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.models import (
    CanonEntity,
    MemoryRecord,
    ManuscriptRevision,
    ManuscriptScene,
    ProjectSummary,
    SceneContract,
    SnowflakeArtifact,
    WritebackProposalCreate,
)


@dataclass(frozen=True)
class ProjectCognitionSnapshot:
    project: ProjectSummary
    artifacts: list[SnowflakeArtifact] = field(default_factory=list)
    canon_entities: list[CanonEntity] = field(default_factory=list)
    scenes: list[SceneContract] = field(default_factory=list)
    memory_records: list[MemoryRecord] = field(default_factory=list)
    manuscript_scenes: list[ManuscriptScene] = field(default_factory=list)


@dataclass(frozen=True)
class WritingScope:
    kind: str
    ref: str
    instruction: str = ""


@dataclass(frozen=True)
class ContextPacket:
    module: str
    title: str
    content: str
    source_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommittedContentEvent:
    source: str
    source_ref: str
    title: str
    content: str
    revision: ManuscriptRevision | None = None


@dataclass(frozen=True)
class ModuleReport:
    module: str
    summary: str
    project_path: Path | None = None
    writeback_proposals: list[WritebackProposalCreate] = field(default_factory=list)


class CognitionModule(Protocol):
    name: str

    def project_path(self, project_id: str) -> Path:
        pass

    def prepare_context(
        self,
        snapshot: ProjectCognitionSnapshot,
        scope: WritingScope,
    ) -> ContextPacket:
        pass

    def ingest_committed_content(
        self,
        snapshot: ProjectCognitionSnapshot,
        event: CommittedContentEvent,
    ) -> ModuleReport:
        pass
