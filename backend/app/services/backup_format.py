"""Bounded, project-isolated decoding shared by backup preview and import."""

import io
import json
import re
import sqlite3
import stat
import zipfile
from pathlib import PurePosixPath
from typing import Any

from app.data.migrations import LATEST_VERSION, run_migrations
from app.services.backup_records import validate_readable_records

BACKUP_KIND = "ai-writing-project-backup"
FORMAT_VERSION = 2
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10_000
TABLES_IN_ORDER = (
    "projects",
    "snowflake_artifacts",
    "snowflake_artifact_revisions",
    "snowflake_artifact_heads",
    "snowflake_record_revisions",
    "snowflake_record_heads",
    "canon_entities",
    "manuscript_chapters",
    "scene_contracts",
    "memory_records",
    "manuscript_proposals",
    "manuscript_scenes",
    "manuscript_revisions",
    "writeback_proposals",
    "reference_suggestions",
    "outbox_jobs",
    "analysis_runs",
    "generation_runs",
    "generation_attempts",
    "scene_proposals",
    "story_facts",
    "story_fact_character_knowledge",
    "knowledge_states",
    "narrative_relations",
    "story_threads",
    "story_thread_events",
)
PRE_GENERATION_RUN_TABLES = tuple(
    table for table in TABLES_IN_ORDER if table not in {"generation_runs", "generation_attempts"}
)
LEGACY_V2_TABLES = tuple(
    table
    for table in PRE_GENERATION_RUN_TABLES
    if table not in {
        "snowflake_artifact_revisions",
        "snowflake_artifact_heads",
        "snowflake_record_revisions",
        "snowflake_record_heads",
    }
)
REVISION_V2_TABLES = tuple(
    table
    for table in PRE_GENERATION_RUN_TABLES
    if table not in {"snowflake_record_revisions", "snowflake_record_heads"}
)
NARRATIVE_TABLES = frozenset(
    {
        "story_facts",
        "story_fact_character_knowledge",
        "knowledge_states",
        "narrative_relations",
        "story_threads",
        "story_thread_events",
    }
)
_DEVICE_NAME = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)


class BackupError(Exception):
    """A package or restore error safe to show to the author."""


class BackupNotFoundError(BackupError):
    pass


class BackupConflictError(BackupError):
    pass


class BackupVersionError(BackupError):
    pass


def validate_project_id(project_id: Any) -> str:
    if (
        not isinstance(project_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", project_id)
        or _DEVICE_NAME.match(project_id)
    ):
        raise BackupError("Invalid project id in backup.")
    return project_id


def validate_module_path(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or str(path) != name
        or any(
            part in {".", ".."}
            or part.endswith((".", " "))
            or re.search(r'[\\:\x00-\x1f<>"|?*]', part)
            or _DEVICE_NAME.match(part)
            for part in path.parts
        )
    ):
        raise BackupError(f"Unsafe module path in package: {name!r}")
    return name


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise BackupError(f"Invalid JSON number: {value}")


def insert_rows(connection: sqlite3.Connection, tables: dict) -> None:
    # Identifiers have been checked against the trusted local schema.
    for table in TABLES_IN_ORDER:
        for row in tables.get(table, []):
            columns = ", ".join(f'"{column}"' for column in row)
            placeholders = ", ".join("?" for _ in row)
            connection.execute(
                f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', list(row.values())
            )


def validate_tables(manifest: dict, tables: Any) -> dict:
    if not isinstance(tables, dict) or set(tables) - set(TABLES_IN_ORDER):
        raise BackupError("Package contains invalid or unknown tables.")
    project_id = manifest["project"]["id"]
    counts = manifest["project"].get("row_counts")
    actual_counts = {table: len(rows) for table, rows in tables.items() if isinstance(rows, list)}
    if (
        not isinstance(counts, dict)
        or any(type(n) is not int or n < 0 for n in counts.values())
        or counts != actual_counts
    ):
        raise BackupError("Manifest row counts do not match the package.")
    if manifest["format_version"] == FORMAT_VERSION:
        schema_version = manifest.get("schema_version", 0)
        expected_tables = (
            TABLES_IN_ORDER
            if schema_version >= 12
            else PRE_GENERATION_RUN_TABLES
            if schema_version >= 11
            else REVISION_V2_TABLES
            if schema_version >= 9
            else LEGACY_V2_TABLES
        )
        if set(tables) != set(expected_tables) or manifest.get("tables") != list(expected_tables):
            raise BackupError("Backup v2 must declare and include every project table.")
    projects = tables.get("projects")
    if not isinstance(projects, list) or len(projects) != 1:
        raise BackupError("Package must contain exactly one project.")
    # A disposable database checks PK/UNIQUE/NOT NULL/FK constraints before any
    # live transaction. Legacy columns can use their migration defaults.
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        run_migrations(connection)
        for table, rows in tables.items():
            if not isinstance(rows, list):
                raise BackupError(f"Invalid rows for {table}.")
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for row in rows:
                if not isinstance(row, dict) or not row or set(row) - columns:
                    raise BackupError(f"Invalid columns in {table}.")
                if row.get("id" if table == "projects" else "project_id") != project_id:
                    raise BackupError(f"Cross-project row in {table}.")
                if any(
                    value is not None and not isinstance(value, (str, int, float))
                    for value in row.values()
                ):
                    raise BackupError(f"Invalid column value in {table}.")
                for column, value in row.items():
                    if column.endswith("_json"):
                        json.loads(
                            value,
                            object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant,
                        )
                if table == "outbox_jobs":
                    payload = json.loads(row.get("payload_json", "{}"))
                    if (
                        not isinstance(payload, dict)
                        or payload.get("project_id", project_id) != project_id
                    ):
                        raise BackupError("Cross-project outbox payload.")
        if projects[0].get("title") != manifest["project"].get("title"):
            raise BackupError("Manifest title does not match the project row.")
        insert_rows(connection, tables)
        validate_readable_records(connection)
    except (sqlite3.Error, ValueError, TypeError, OverflowError, RecursionError, KeyError) as exc:
        raise BackupError("Package rows violate the project schema or references.") from exc
    finally:
        connection.close()
    return tables


def read_package(package: bytes) -> tuple[dict, dict, list[tuple[str, bytes]]]:
    if len(package) > MAX_PACKAGE_BYTES:
        raise BackupError("Backup ZIP exceeds the 64 MiB upload limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(package)) as bundle:
            members = bundle.infolist()
            if (
                len(members) > MAX_MEMBERS
                or sum(item.file_size for item in members) > MAX_EXPANDED_BYTES
            ):
                raise BackupError("Backup exceeds the expanded size or file count limit.")
            seen = set()
            module_files = []
            raw = {}
            for item in members:
                name = item.filename
                if item.orig_filename != name:
                    raise BackupError("ZIP member names must use canonical relative paths.")
                if name.casefold() in seen:
                    raise BackupError("Duplicate ZIP member.")
                seen.add(name.casefold())
                if item.is_dir() or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                    raise BackupError(
                        "ZIP directories, links and encrypted members are not supported."
                    )
                if name not in {"manifest.json", "data.json"}:
                    if not name.startswith("modules/"):
                        raise BackupError(f"Unknown ZIP member: {name}")
                    validate_module_path(name[8:])
                content = bundle.read(item)
                content.decode("utf-8")
                if name.startswith("modules/"):
                    module_files.append((name[8:], content))
                else:
                    raw[name] = json.loads(
                        content, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
                    )
    except (
        zipfile.BadZipFile,
        UnicodeError,
        ValueError,
        RuntimeError,
        NotImplementedError,
        RecursionError,
    ) as exc:
        raise BackupError("Package is not a valid UTF-8 project ZIP.") from exc
    manifest = raw.get("manifest.json")
    payload = raw.get("data.json")
    if not isinstance(manifest, dict) or not isinstance(payload, dict):
        raise BackupError("Package must contain manifest.json and data.json objects.")
    if (
        manifest.get("kind") != BACKUP_KIND
        or type(manifest.get("format_version")) is not int
        or manifest["format_version"] not in (1, FORMAT_VERSION)
    ):
        raise BackupVersionError("Unsupported project backup format.")
    schema_version = manifest.get("schema_version")
    if type(schema_version) is not int or not 1 <= schema_version <= LATEST_VERSION:
        raise BackupVersionError("Backup schema version is incompatible with this application.")
    if not isinstance(manifest.get("project"), dict):
        raise BackupError("Manifest is missing the project identity.")
    validate_project_id(manifest["project"].get("id"))
    if type(manifest.get("module_file_count")) is not int or manifest["module_file_count"] != len(
        module_files
    ):
        raise BackupError("Manifest module count does not match the ZIP.")
    names = {name.casefold() for name, _ in module_files}
    if any(
        str(parent).casefold() in names
        for name, _ in module_files
        for parent in PurePosixPath(name).parents
    ):
        raise BackupError("Module paths contain a file/directory collision.")
    return manifest, validate_tables(manifest, payload.get("tables")), module_files
