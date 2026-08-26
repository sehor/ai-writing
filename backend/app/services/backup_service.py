"""Project backup / restore packages (P2-07).

A backup is a ZIP archive with three members:

- ``manifest.json`` — kind marker, format/schema versions, project identity,
  per-table row counts, exported timestamp;
- ``data.json`` — every project-scoped table dumped as ordered row lists
  (insertion order matches foreign-key dependencies);
- ``modules/<relative path>`` — the file-backed knowledge stores under the
  project's module root (LLM Wiki sources, memplace prose samples, ...).

Import validates format + schema compatibility up front, replaces the
project atomically inside one unit of work (the ``projects`` row cascades
every child table), and restores module files after the commit.
"""

import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from app.data import SQLiteWritingDataStore
from app.data.helpers import utc_now
from app.data.migrations import LATEST_VERSION
from app.data.unit_of_work import SqliteUnitOfWork

BACKUP_KIND = "ai-writing-project-backup"
FORMAT_VERSION = 1
MIN_SCHEMA_VERSION = 1

# Insertion order respects FK dependencies; every table carries project_id
# except the root projects row.
TABLES_IN_ORDER: tuple[str, ...] = (
    "projects",
    "snowflake_artifacts",
    "canon_entities",
    "scene_contracts",
    "manuscript_chapters",
    "memory_records",
    "manuscript_proposals",
    "manuscript_scenes",
    "manuscript_revisions",
    "writeback_proposals",
    "reference_suggestions",
    "outbox_jobs",
    "analysis_runs",
    "scene_proposals",
)


class BackupError(Exception):
    """Base class: message is safe to surface to API clients."""


class BackupNotFoundError(BackupError):
    pass


class BackupConflictError(BackupError):
    pass


class BackupVersionError(BackupError):
    pass


class ProjectBackupService:
    def __init__(self, data_store: SQLiteWritingDataStore, projects_root: Path):
        self.data_store = data_store
        self.projects_root = projects_root

    # -- export ----------------------------------------------------------

    def export_package(self, project_id: str) -> bytes:
        """Build the ZIP package for one project; raises if unknown."""
        with self.data_store.connect() as connection:
            row = connection.execute(
                "SELECT title FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            if row is None:
                raise BackupNotFoundError(f"Project '{project_id}' does not exist.")
            title = row[0]
            counts: dict[str, int] = {}
            tables: dict[str, list[dict[str, Any]]] = {}
            for table in TABLES_IN_ORDER:
                column = "id" if table == "projects" else "project_id"
                rows = [
                    dict(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table} WHERE {column} = ? ORDER BY rowid",
                        (project_id,),
                    )
                ]
                if rows:
                    tables[table] = rows
                    counts[table] = len(rows)

        module_files = self._collect_module_files(project_id)
        manifest = {
            "kind": BACKUP_KIND,
            "format_version": FORMAT_VERSION,
            "schema_version": LATEST_VERSION,
            "exported_at": utc_now(),
            "project": {
                "id": project_id,
                "title": title,
                "row_counts": counts,
            },
            "module_file_count": len(module_files),
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            bundle.writestr(
                "data.json",
                json.dumps({"tables": tables}, ensure_ascii=False),
            )
            for relative_path, content in module_files:
                bundle.writestr(f"modules/{relative_path}", content)
        return buffer.getvalue()

    # -- preview ---------------------------------------------------------

    def preview_import(self, package: bytes) -> dict[str, Any]:
        """Validate a package and report what an import would change."""
        manifest, tables, module_names = self._read_package(package)
        project_id = manifest["project"]["id"]
        with self.data_store.connect() as connection:
            exists = (
                connection.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
                is not None
            )
        return {
            "project": {
                "id": project_id,
                "title": manifest["project"]["title"],
                "row_counts": manifest["project"]["row_counts"],
            },
            "schema_version": manifest["schema_version"],
            "current_schema_version": LATEST_VERSION,
            "module_file_count": len(module_names),
            "target_exists": exists,
            "would_replace_existing_project": exists,
        }

    # -- import ----------------------------------------------------------

    def import_package(self, package: bytes, *, overwrite: bool = False) -> dict[str, Any]:
        manifest, tables, module_files = self._read_package(package)
        project_id = manifest["project"]["id"]

        with self.data_store.connect() as connection:
            exists = (
                connection.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
                is not None
            )
        if exists and not overwrite:
            raise BackupConflictError(
                f"Project '{project_id}' already exists; pass overwrite to replace it."
            )

        inserted: dict[str, int] = {}
        with SqliteUnitOfWork(self.data_store.database_path) as uow:
            connection = uow.connection
            if exists:
                # Children cascade from the projects row (FK ON in UoW).
                connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            for table in TABLES_IN_ORDER:
                rows = tables.get(table, [])
                for row_values in rows:
                    columns = list(row_values.keys())
                    placeholders = ", ".join("?" for _ in columns)
                    connection.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                        [row_values[column] for column in columns],
                    )
                if rows:
                    inserted[table] = len(rows)

        project_modules_dir = self._project_modules_dir(project_id)
        if project_modules_dir.exists():
            shutil.rmtree(project_modules_dir)
        for relative_path, content in module_files:
            target = (project_modules_dir / relative_path).resolve()
            resolved_root = project_modules_dir.resolve()
            if resolved_root != target and resolved_root not in target.parents:
                raise BackupError(f"Unsafe module path in package: {relative_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        return {
            "project": manifest["project"],
            "replaced_existing": exists,
            "restored_tables": inserted,
            "restored_module_files": len(module_files),
        }

    # -- internals -------------------------------------------------------

    def _project_modules_dir(self, project_id: str) -> Path:
        if not project_id or "/" in project_id or "\\" in project_id or ".." in project_id:
            raise BackupError(f"Invalid project id: {project_id!r}")
        return self.projects_root / project_id / "modules"

    def _collect_module_files(self, project_id: str) -> list[tuple[str, str]]:
        modules_dir = self._project_modules_dir(project_id)
        if not modules_dir.exists():
            return []
        collected: list[tuple[str, str]] = []
        for path in sorted(modules_dir.rglob("*")):
            if path.is_file():
                collected.append(
                    (path.relative_to(modules_dir).as_posix(), path.read_text(encoding="utf-8"))
                )
        return collected

    def _read_package(
        self, package: bytes
    ) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], list[tuple[str, str]]]:
        try:
            bundle = zipfile.ZipFile(io.BytesIO(package))
        except zipfile.BadZipFile as exc:
            raise BackupError("Package is not a valid ZIP archive.") from exc
        try:
            manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
            payload = json.loads(bundle.read("data.json").decode("utf-8"))
        except KeyError as exc:
            raise BackupError(f"Package is missing {exc.args[0]}.") from exc
        except json.JSONDecodeError as exc:
            raise BackupError(f"Package JSON is malformed: {exc}") from exc

        self._validate_manifest(manifest)

        tables = payload.get("tables", {})
        unknown = set(tables) - set(TABLES_IN_ORDER)
        if unknown:
            raise BackupError(f"Package contains unknown tables: {sorted(unknown)}")

        module_files: list[tuple[str, str]] = []
        for name in bundle.namelist():
            if not name.startswith("modules/") or name.endswith("/"):
                continue
            module_files.append((name[len("modules/") :], bundle.read(name).decode("utf-8")))
        expected_modules = manifest.get("module_file_count")
        if expected_modules is not None and expected_modules != len(module_files):
            raise BackupError(
                f"Manifest claims {expected_modules} module files but the package has {len(module_files)}."
            )
        return manifest, tables, module_files

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        if manifest.get("kind") != BACKUP_KIND:
            raise BackupError("Not an AI Writing Studio project backup.")
        if manifest.get("format_version") != FORMAT_VERSION:
            raise BackupError(
                f"Unsupported backup format version: {manifest.get('format_version')!r}."
            )
        schema_version = manifest.get("schema_version")
        if not isinstance(schema_version, int) or not (
            MIN_SCHEMA_VERSION <= schema_version <= LATEST_VERSION
        ):
            raise BackupVersionError(
                f"Backup schema version {schema_version!r} is incompatible with this "
                f"application (supported {MIN_SCHEMA_VERSION}..{LATEST_VERSION})."
            )
        project = manifest.get("project")
        if not isinstance(project, dict) or not project.get("id"):
            raise BackupError("Manifest is missing the project identity.")
