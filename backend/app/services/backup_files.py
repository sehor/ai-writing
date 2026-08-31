"""Journal module replacement until SQLite decides whether it committed."""

import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.observability import log_event
from app.services.backup_format import BackupError
from app.services.backup_recovery import (
    JOURNAL,
    PREFIX,
    cleanup_staging,
    is_link,
    read_journal,
    recover_operation,
    sync_directory,
    write_journal,
)


def checked_modules_dir(projects_root: Path, project_id: str) -> Path:
    root = projects_root.resolve()
    target = root / project_id / "modules"
    for path in (target.parent, target):
        if is_link(path):
            raise BackupError("Project module directories must not be links.")
        if path.exists() and not path.is_dir():
            raise BackupError("Project module path is not a directory.")
    if not target.resolve().is_relative_to(root):
        raise BackupError("Project module directory escapes the project root.")
    return target


class ModuleRestore:
    def __init__(self, projects_root: Path, database_path: Path, project_id: str):
        self.target = checked_modules_dir(projects_root, project_id)
        if any(is_link(path) for path in self.target.rglob("*")):
            raise BackupError("Cannot replace linked module files or directories.")
        self.projects_root = projects_root
        self.database_path = database_path
        self.operation_id = uuid4().hex
        self.staging = projects_root / (PREFIX + self.operation_id)
        self.record = {
            "version": 1,
            "operation_id": self.operation_id,
            "project_id": project_id,
            "database": str(database_path.resolve()),
            "phase": "staging",
            "had_modules": self.target.exists(),
            "created_parent": not self.target.parent.exists(),
        }

    def prepare(self, files: list[tuple[str, bytes]]) -> None:
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir()
        sync_directory(self.projects_root)
        write_journal(self.staging, self.record)
        prepared = self.staging / "new"
        prepared.mkdir()
        for name, content in files:
            path = prepared / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
        directories = [prepared, *(path for path in prepared.rglob("*") if path.is_dir())]
        for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            sync_directory(path)
        sync_directory(self.staging)

    def record_commit(self, connection) -> None:
        connection.execute(
            "INSERT INTO backup_restore_commits(operation_id, target_project) VALUES (?, ?)",
            (self.operation_id, self.record["project_id"]),
        )

    def __call__(self) -> None:
        checked_modules_dir(self.projects_root, self.record["project_id"])
        self.record = {**self.record, "phase": "installing"}
        write_journal(self.staging, self.record)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        sync_directory(self.projects_root)
        if self.target.exists():
            self.target.rename(self.staging / "old")
            sync_directory(self.target.parent)
            sync_directory(self.staging)
        (self.staging / "new").rename(self.target)
        sync_directory(self.target.parent)
        sync_directory(self.staging)

    def finish(self) -> bool:
        record = read_journal(self.staging, self.database_path)
        return recover_operation(self.staging, self.database_path, self.target, record)


@contextmanager
def staged_modules(
    projects_root: Path, project_id: str, files: list[tuple[str, bytes]], *, database_path: Path
):
    restore = ModuleRestore(projects_root, database_path, project_id)
    try:
        restore.prepare(files)
        yield restore
    except BaseException as exc:
        if not restore.staging.exists():
            raise
        if not (restore.staging / JOURNAL).exists():
            cleanup_staging(restore.staging)
            raise
        was_committed = restore.finish()
        if not was_committed or not isinstance(exc, Exception):
            raise
        # A commit acknowledgment can fail AFTER the transaction committed.
        # SQLite's durable marker wins: never roll the files back in that case.
        log_event(
            "backup_commit_acknowledgment",
            project_id=project_id,
            result="committed",
            error_code=type(exc).__name__,
        )
    else:
        if not restore.finish():
            raise BackupError("Restore was not committed; original project state was recovered.")
