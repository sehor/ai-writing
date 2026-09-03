"""Complete project snapshots with validated, compensating file restoration."""

import io
import json
import sqlite3
import zipfile
from pathlib import Path

from app.data import SQLiteWritingDataStore
from app.data.helpers import utc_now
from app.data.migrations import LATEST_VERSION
from app.data.project_operations import project_operation
from app.data.unit_of_work import SqliteUnitOfWork
from app.services.backup_files import checked_modules_dir, staged_modules
from app.services.backup_recovery import recover_pending, restore_lock
from app.services.backup_format import (
    BACKUP_KIND,
    FORMAT_VERSION,
    MAX_PACKAGE_BYTES,
    MAX_EXPANDED_BYTES,
    MAX_MEMBERS,
    TABLES_IN_ORDER,
    BackupConflictError,
    BackupError,
    BackupNotFoundError,
    BackupVersionError,
    insert_rows,
    read_package,
    validate_module_path,
    validate_project_id,
)
from app.data.migrations import backfill_legacy_snowflake_artifacts

__all__ = [
    "ProjectBackupService",
    "BackupError",
    "BackupConflictError",
    "BackupNotFoundError",
    "BackupVersionError",
    "TABLES_IN_ORDER",
    "FORMAT_VERSION",
    "BACKUP_KIND",
]


class ProjectBackupService:
    def __init__(self, data_store: SQLiteWritingDataStore, projects_root: Path):
        self.data_store = data_store
        self.projects_root = projects_root

    def export_package(self, project_id: str) -> bytes:
        validate_project_id(project_id)
        with project_operation(project_id), self.data_store.connect() as connection:
            # The connection context does not start a transaction for SELECT.
            # Pin every table to one WAL snapshot; author writes can continue.
            connection.execute("BEGIN")
            tables = {
                table: [
                    dict(row)
                    for row in connection.execute(
                        f'SELECT * FROM "{table}" WHERE {"id" if table == "projects" else "project_id"} = ? ORDER BY rowid',
                        (project_id,),
                    )
                ]
                for table in TABLES_IN_ORDER
            }
            if not tables["projects"]:
                raise BackupNotFoundError(f"Project '{project_id}' does not exist.")
            files = self._collect_module_files(project_id)
            manifest = {
                "kind": BACKUP_KIND,
                "format_version": FORMAT_VERSION,
                "schema_version": LATEST_VERSION,
                "exported_at": utc_now(),
                "tables": list(TABLES_IN_ORDER),
                "project": {
                    "id": project_id,
                    "title": tables["projects"][0]["title"],
                    "row_counts": {table: len(rows) for table, rows in tables.items()},
                },
                "module_file_count": len(files),
            }
        buffer = io.BytesIO()
        metadata = {
            "manifest.json": json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            "data.json": json.dumps({"tables": tables}, ensure_ascii=False).encode("utf-8"),
        }
        if (
            len(files) + 2 > MAX_MEMBERS
            or sum(map(len, metadata.values())) + sum(len(content) for _, content in files)
            > MAX_EXPANDED_BYTES
        ):
            raise BackupError("Project exceeds the supported backup size or file count limit.")
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, content in metadata.items():
                bundle.writestr(name, content)
            for name, content in files:
                bundle.writestr(f"modules/{name}", content)
        package = buffer.getvalue()
        if len(package) > MAX_PACKAGE_BYTES:
            raise BackupError("Project exceeds the supported 64 MiB ZIP limit.")
        return package

    def _target_exists(self, connection: sqlite3.Connection, project_id: str) -> bool:
        identities = connection.execute(
            "SELECT id FROM projects WHERE lower(id) = lower(?)", (project_id,)
        ).fetchall()
        if any(row["id"] != project_id for row in identities):
            raise BackupConflictError("Project id collides with another project's directory name.")
        # An orphaned module directory still contains author data and needs confirmation.
        return bool(identities) or checked_modules_dir(self.projects_root, project_id).exists()

    def preview_import(self, package: bytes) -> dict:
        manifest, _, files = read_package(package)
        project_id = manifest["project"]["id"]
        checked_modules_dir(self.projects_root, project_id)
        with self.data_store.connect() as connection:
            exists = self._target_exists(connection, project_id)
        legacy = manifest["format_version"] == 1
        return {
            "project": manifest["project"],
            "schema_version": manifest["schema_version"],
            "current_schema_version": LATEST_VERSION,
            "format_version": manifest["format_version"],
            "module_file_count": len(files),
            "target_exists": exists,
            "would_replace_existing_project": exists,
            "legacy_incomplete": legacy,
            "can_overwrite": not legacy,
            "warnings": ["旧版 v1 备份可能缺少 Narrative 数据，只允许导入为不存在的项目。"]
            if legacy
            else [],
        }

    def import_package(self, package: bytes, *, overwrite: bool = False) -> dict:
        manifest, tables, files = read_package(package)
        legacy = manifest["format_version"] == 1
        with restore_lock:
            self.recover_interrupted_imports()
            return self._import_validated(
                manifest, tables, files, overwrite=overwrite, legacy=legacy
            )

    def recover_interrupted_imports(self) -> int:
        with restore_lock:
            try:
                return recover_pending(self.data_store.database_path, self.projects_root)
            except (OSError, sqlite3.Error) as exc:
                raise BackupError(
                    "Interrupted restore recovery failed. Preserve .restore-* directories and "
                    "stop other processes using this data root before retrying."
                ) from exc

    def _import_validated(self, manifest, tables, files, *, overwrite: bool, legacy: bool) -> dict:
        project_id = manifest["project"]["id"]
        with project_operation(project_id):
            try:
                with staged_modules(
                    self.projects_root,
                    project_id,
                    files,
                    database_path=self.data_store.database_path,
                ) as install:
                    with SqliteUnitOfWork(self.data_store.database_path) as uow:
                        uow.connection.execute("PRAGMA synchronous = FULL")
                        uow.connection.execute("BEGIN IMMEDIATE")
                        exists = self._target_exists(uow.connection, project_id)
                        if exists and (not overwrite or legacy):
                            raise BackupConflictError(
                                "Legacy v1 backups cannot overwrite an existing project."
                                if legacy
                                else "Project already exists; confirm overwrite first."
                            )
                        self._restore_database(uow.connection, project_id, tables)
                        install.record_commit(uow.connection)
                        install()
                    # Commit succeeded; only now discard the retained directory.
            except (OSError, sqlite3.Error) as exc:
                raise BackupError(
                    "Restore did not finish. Preserve any .restore-* directories and restart "
                    "the backend to reconcile recovery state before retrying."
                ) from exc
        return {
            "project": manifest["project"],
            "replaced_existing": exists,
            "format_version": manifest["format_version"],
            "legacy_incomplete": legacy,
            "restored_tables": {table: len(rows) for table, rows in tables.items()},
            "restored_module_files": len(files),
        }

    def _restore_database(self, connection: sqlite3.Connection, project_id: str, tables: dict):
        connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        insert_rows(connection, tables)
        if "snowflake_artifact_revisions" not in tables:
            backfill_legacy_snowflake_artifacts(connection, project_id)
        connection.execute(
            "UPDATE outbox_jobs SET status = 'pending', processing_started_at = '' WHERE project_id = ? AND status = 'processing'",
            (project_id,),
        )

    def _collect_module_files(self, project_id: str) -> list[tuple[str, bytes]]:
        modules = checked_modules_dir(self.projects_root, project_id)
        files = []
        size = 0
        names = set()
        for path in sorted(modules.rglob("*")):
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise BackupError("Cannot export linked module files or directories.")
            if path.is_file():
                name = validate_module_path(path.relative_to(modules).as_posix())
                if name.casefold() in names:
                    raise BackupError("Module filenames collide on case-insensitive filesystems.")
                names.add(name.casefold())
                size += path.stat().st_size
                if size > MAX_EXPANDED_BYTES or len(names) + 2 > MAX_MEMBERS:
                    raise BackupError("Module files exceed the supported backup limits.")
                content = path.read_bytes()
                try:
                    content.decode("utf-8")
                except UnicodeError as exc:
                    raise BackupError("Module files must be UTF-8 text.") from exc
                files.append((name, content))
        return files
