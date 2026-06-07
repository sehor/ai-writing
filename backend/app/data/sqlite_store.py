from pathlib import Path
from re import sub
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import sqlite3
from typing import Iterator, Protocol

from app.models import (
    CanonEntity,
    CanonEntityCreate,
    CanonEntityUpdate,
    MemoryRecord,
    MemoryRecordCreate,
    MemoryRecordUpdate,
    ManuscriptChapter,
    ManuscriptChapterCreate,
    ManuscriptChapterUpdate,
    ManuscriptProposal,
    ManuscriptProposalCreate,
    ManuscriptProposalStatus,
    ManuscriptRevision,
    ManuscriptScene,
    ManuscriptSceneUpdate,
    ProjectCreate,
    ProjectSummary,
    ReferenceSuggestion,
    ReferenceSuggestionCreate,
    ReferenceSuggestionStatus,
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
    SnowflakeArtifact,
    WorkflowAgentTrace,
    WritebackProposal,
    WritebackProposalCreate,
    WritebackProposalStatus,
)
from app.data.mixins.projects import ProjectsDataMixin
from app.data.mixins.artifacts import ArtifactsDataMixin
from app.data.mixins.canon import CanonDataMixin
from app.data.mixins.scenes import ScenesDataMixin
from app.data.mixins.manuscript import ManuscriptDataMixin
from app.data.mixins.memory import MemoryDataMixin
from app.data.mixins.wiki import WikiDataMixin
from app.data.interfaces import WritingDataStore

class SQLiteWritingDataStore(
    ProjectsDataMixin,
    ArtifactsDataMixin,
    CanonDataMixin,
    ScenesDataMixin,
    ManuscriptDataMixin,
    MemoryDataMixin,
    WikiDataMixin,
):
    def __init__(self, database_path: Path):
        self.database_path = database_path
