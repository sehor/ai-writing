"""Unit of Work: one SQLite connection coordinating several repositories.

SqliteUnitOfWork opens a single connection with the same PRAGMAs the
legacy connect() helper used (WAL journal, foreign keys enforced), hands
out repository instances bound to that connection, and owns the
transaction boundary: clean exit commits, an exception rolls back.
commit()/rollback() can also be called explicitly for multi-phase work.
"""

import sqlite3
from pathlib import Path
from typing import Callable

from app.data.repositories.analysis import AnalysisRepository
from app.data.repositories.canon import CanonRepository
from app.data.repositories.manuscript import ManuscriptRepository
from app.data.repositories.memory import MemoryRepository
from app.data.repositories.narrative import NarrativeRepository
from app.data.repositories.outbox import OutboxRepository
from app.data.repositories.projects import ProjectRepository
from app.data.repositories.review import ReviewRepository
from app.data.repositories.scene_proposals import SceneProposalRepository
from app.data.repositories.scenes import SceneRepository
from app.data.repositories.snowflake import SnowflakeRepository


def open_connection(database_path: Path) -> sqlite3.Connection:
    """Open a store connection with the standard row factory and PRAGMAs."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class SqliteUnitOfWork:
    """One shared connection plus every repository bound to it."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self._connection: sqlite3.Connection | None = None
        self._repositories: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Transaction boundary
    # ------------------------------------------------------------------

    def __enter__(self) -> "SqliteUnitOfWork":
        self._connection = open_connection(self.database_path)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._repositories.clear()
        # Never swallow the exception that triggered the rollback.
        return False

    def commit(self) -> None:
        self._require_connection().commit()

    def rollback(self) -> None:
        self._require_connection().rollback()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._require_connection()

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("SqliteUnitOfWork is not active; use it as a context manager.")
        return self._connection

    # ------------------------------------------------------------------
    # Repositories bound to the shared connection
    # ------------------------------------------------------------------

    def _repository(self, name: str, factory: Callable[[sqlite3.Connection], object]) -> object:
        repository = self._repositories.get(name)
        if repository is None:
            repository = factory(self._require_connection())
            self._repositories[name] = repository
        return repository

    @property
    def projects(self) -> ProjectRepository:
        return self._repository("projects", ProjectRepository)

    @property
    def snowflake(self) -> SnowflakeRepository:
        return self._repository("snowflake", SnowflakeRepository)

    @property
    def canon(self) -> CanonRepository:
        return self._repository("canon", CanonRepository)

    @property
    def scenes(self) -> SceneRepository:
        return self._repository("scenes", SceneRepository)

    @property
    def scene_proposals(self) -> SceneProposalRepository:
        return self._repository("scene_proposals", SceneProposalRepository)

    @property
    def manuscripts(self) -> ManuscriptRepository:
        return self._repository("manuscripts", ManuscriptRepository)

    @property
    def memory(self) -> MemoryRepository:
        return self._repository("memory", MemoryRepository)

    @property
    def review(self) -> ReviewRepository:
        return self._repository("review", ReviewRepository)

    @property
    def narrative(self) -> NarrativeRepository:
        return self._repository("narrative", NarrativeRepository)

    @property
    def outbox(self) -> OutboxRepository:
        return self._repository("outbox", OutboxRepository)

    @property
    def analysis(self) -> AnalysisRepository:
        return self._repository("analysis", AnalysisRepository)
