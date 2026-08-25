"""Focused per-aggregate repositories for the SQLite store (P2-03).

Every repository is constructed with an open sqlite3.Connection and owns
the SQL for exactly one aggregate family. Repositories never commit or
open connections; transaction boundaries belong to
app.data.unit_of_work.SqliteUnitOfWork, which exposes these repositories
as properties bound to its shared connection.
"""

from app.data.repositories.analysis import AnalysisRepository
from app.data.repositories.canon import CanonRepository, ConcurrentCanonUpdateError
from app.data.repositories.manuscript import ManuscriptRepository
from app.data.repositories.memory import MemoryRepository
from app.data.repositories.outbox import OutboxRepository
from app.data.repositories.projects import ProjectRepository
from app.data.repositories.review import ReviewRepository
from app.data.repositories.scene_proposals import (
    SceneChapterMissingError,
    SceneProposalNotFoundError,
    SceneProposalReviewedError,
    SceneProposalRepository,
    SceneSequenceConflictError,
)
from app.data.repositories.scenes import SceneRepository
from app.data.repositories.snowflake import SnowflakeRepository

__all__ = [
    "AnalysisRepository",
    "CanonRepository",
    "ConcurrentCanonUpdateError",
    "ManuscriptRepository",
    "MemoryRepository",
    "OutboxRepository",
    "ProjectRepository",
    "ReviewRepository",
    "SceneChapterMissingError",
    "SceneProposalNotFoundError",
    "SceneProposalReviewedError",
    "SceneProposalRepository",
    "SceneSequenceConflictError",
    "SceneRepository",
    "SnowflakeRepository",
]
