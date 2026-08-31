"""Restartable filesystem recovery, decided by the SQLite commit marker.

Runs before serving requests/starting the dispatcher. Only one application
process may use a data root. Unknown or damaged journals fail closed.
"""

import json
import os
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock

from app.data.project_operations import project_operation
from app.data.unit_of_work import open_connection
from app.observability import log_event
from app.services.backup_format import BackupError, validate_project_id

PREFIX = ".restore-v1-"
JOURNAL = "journal.json"
# Only restores need process-wide serialization; ordinary authoring stays local
# to its project lock. Recovery must never inspect another active restore.
restore_lock = RLock()


def is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def sync_directory(path: Path) -> None:
    # Python does not expose a portable Windows directory fsync. File contents
    # are flushed on both platforms; do not claim hardware power-loss atomicity.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_journal(staging: Path, record: dict) -> None:
    temporary = staging / "journal.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(staging / JOURNAL)
    sync_directory(staging)


def read_journal(staging: Path, database_path: Path) -> dict:
    try:
        journal = staging / JOURNAL
        if is_link(staging) or is_link(journal) or journal.stat().st_size > 4096:
            raise ValueError("Invalid journal file")
        record = json.loads(journal.read_text(encoding="utf-8"))
        if (
            not isinstance(record, dict)
            or set(record)
            != {
                "version",
                "operation_id",
                "project_id",
                "database",
                "phase",
                "had_modules",
                "created_parent",
            }
            or type(record["version"]) is not int
            or record["version"] != 1
            or not isinstance(record["operation_id"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", record["operation_id"])
            or staging.name != PREFIX + record["operation_id"]
            or record["phase"] not in ("staging", "installing", "rolled_back")
            or type(record["had_modules"]) is not bool
            or type(record["created_parent"]) is not bool
            or record["database"] != str(database_path.resolve())
        ):
            raise ValueError("Invalid journal identity or phase")
        validate_project_id(record["project_id"])
        validate_staging(staging)
        return record
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise BackupError(
            f"Unsafe or incomplete restore journal; preserve {staging} for recovery."
        ) from exc


def validate_staging(staging: Path) -> None:
    # Validate every deletion/rename target before touching it. No links, even
    # in old module copies or unexpected locally modified journal directories.
    allowed = {JOURNAL, "journal.tmp", "new", "old", "failed"}
    if is_link(staging) or any(child.name not in allowed for child in staging.iterdir()):
        raise BackupError(f"Unexpected restore files; preserve {staging} for recovery.")
    for path in staging.rglob("*"):
        if is_link(path) or not path.resolve().is_relative_to(staging.resolve()):
            raise BackupError(f"Linked restore files; preserve {staging} for recovery.")


def committed(database_path: Path, record: dict) -> bool:
    with closing(open_connection(database_path)) as connection, connection:
        row = connection.execute(
            "SELECT target_project FROM backup_restore_commits WHERE operation_id = ?",
            (record["operation_id"],),
        ).fetchone()
        if row is not None and row[0] != record["project_id"]:
            raise BackupError("Restore commit marker does not match the journal project.")
        return row is not None


def forget_commit(database_path: Path, operation_id: str) -> None:
    with closing(open_connection(database_path)) as connection, connection:
        connection.execute(
            "DELETE FROM backup_restore_commits WHERE operation_id = ?", (operation_id,)
        )


def cleanup_staging(staging: Path) -> None:
    validate_staging(staging)
    # The journal is removed LAST. A kill during recursive cleanup remains
    # recoverable; an empty directory after journal unlink is safe to discard.
    for child in staging.iterdir():
        if child.name == JOURNAL:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    (staging / JOURNAL).unlink(missing_ok=True)
    staging.rmdir()
    sync_directory(staging.parent)


def recover_operation(staging: Path, database_path: Path, target: Path, record: dict) -> bool:
    validate_staging(staging)
    was_committed = committed(database_path, record)
    prepared, previous, failed = (staging / name for name in ("new", "old", "failed"))
    if was_committed:
        if record["phase"] != "installing" or not target.is_dir() or prepared.exists():
            raise BackupError(f"Committed restore files are incomplete; preserve {staging}.")
    elif record["phase"] == "installing":
        if record["had_modules"]:
            if previous.exists():
                if target.exists():
                    if failed.exists():
                        raise BackupError(f"Ambiguous rollback directories; preserve {staging}.")
                    target.rename(failed)
                    sync_directory(target.parent)
                    sync_directory(staging)
                previous.rename(target)
                sync_directory(target.parent)
                sync_directory(staging)
            elif not target.is_dir():
                raise BackupError(f"Original module directory is missing; preserve {staging}.")
        elif not prepared.exists() and not failed.exists() and target.exists():
            target.rename(failed)
            sync_directory(target.parent)
            sync_directory(staging)
        # Record completion before removing the rename evidence. Later author
        # writes must never be mistaken for uncommitted imported module files.
        record = {**record, "phase": "rolled_back"}
        write_journal(staging, record)
    if not was_committed and record["created_parent"] and target.parent.exists():
        # Never remove other files created by the author or another module.
        if not any(target.parent.iterdir()):
            target.parent.rmdir()
    try:
        cleanup_staging(staging)
        forget_commit(database_path, record["operation_id"])
    except (OSError, sqlite3.Error) as exc:
        # Core state is already consistent; retain evidence and retry cleanup
        # on startup. A cleanup failure is not a failed authoring transaction.
        log_event(
            "backup_recovery_cleanup",
            project_id=record["project_id"],
            result="deferred",
            error_code=type(exc).__name__,
        )
    return was_committed


def recover_pending(database_path: Path, projects_root: Path) -> int:
    from app.services.backup_files import checked_modules_dir

    if not projects_root.exists():
        return 0
    recovered = 0
    for staging in sorted(projects_root.glob(".restore-*")):
        if is_link(staging) or not staging.is_dir():
            raise BackupError(f"Invalid restore directory; preserve {staging}.")
        if not re.fullmatch(re.escape(PREFIX) + r"[0-9a-f]{32}", staging.name):
            raise BackupError(f"Legacy restore requires manual recovery; preserve {staging}.")
        if not (staging / JOURNAL).exists():
            # A stop before the initial journal was published, or after cleanup.
            if {item.name for item in staging.iterdir()} - {"journal.tmp"}:
                raise BackupError(f"Missing restore journal; preserve {staging}.")
            cleanup_staging(staging)
            forget_commit(database_path, staging.name[len(PREFIX) :])
            continue
        record = read_journal(staging, database_path)
        with project_operation(record["project_id"]):
            target = checked_modules_dir(projects_root, record["project_id"])
            outcome = recover_operation(staging, database_path, target, record)
            recovered += 1
            log_event(
                "backup_recovery",
                project_id=record["project_id"],
                operation_id=record["operation_id"],
                result="committed" if outcome else "rolled_back",
            )
    # A stop after filesystem cleanup but before marker deletion leaves a harmless
    # marker. Remove only markers whose matching directory no longer exists.
    with closing(open_connection(database_path)) as connection, connection:
        for row in connection.execute("SELECT operation_id FROM backup_restore_commits").fetchall():
            if (
                re.fullmatch(r"[0-9a-f]{32}", row[0])
                and not (projects_root / (PREFIX + row[0])).exists()
            ):
                connection.execute(
                    "DELETE FROM backup_restore_commits WHERE operation_id = ?", (row[0],)
                )
    return recovered
