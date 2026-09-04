"""Safe persistence for model generation runs and attempts."""

import sqlite3
from uuid import uuid4

from app.models import (
    GenerationAttempt,
    GenerationAttemptCreate,
    GenerationRun,
    GenerationRunCreate,
    GenerationRunUpdate,
)


RUN_COLUMNS = """
    SELECT id, project_id, use_case, prompt_id, prompt_version, schema_name,
           schema_version, requested_profile_id, final_profile_id, provider,
           model, status, error_code, safe_error, allow_fallback, allow_repair,
           attempt_count, repair_count, fallback_count, input_tokens,
           output_tokens, duration_ms, created_at, completed_at
    FROM generation_runs
"""

ATTEMPT_COLUMNS = """
    SELECT id, project_id, run_id, attempt_index, attempt_kind, profile_id, provider,
           model, status, error_code, retryable, duration_ms, finish_reason,
           input_tokens, output_tokens, created_at
    FROM generation_attempts
"""


def _attempt_from_row(row: sqlite3.Row) -> GenerationAttempt:
    return GenerationAttempt(
        id=row["id"],
        run_id=row["run_id"],
        attempt_index=row["attempt_index"],
        attempt_kind=row["attempt_kind"],
        profile_id=row["profile_id"],
        provider=row["provider"],
        model=row["model"],
        status=row["status"],
        error_code=row["error_code"],
        retryable=bool(row["retryable"]),
        duration_ms=row["duration_ms"],
        finish_reason=row["finish_reason"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        created_at=row["created_at"],
    )


def _run_from_row(row: sqlite3.Row, attempts: list[GenerationAttempt]) -> GenerationRun:
    return GenerationRun(
        id=row["id"],
        project_id=row["project_id"],
        use_case=row["use_case"],
        prompt_id=row["prompt_id"],
        prompt_version=row["prompt_version"],
        schema_name=row["schema_name"],
        schema_version=row["schema_version"],
        requested_profile_id=row["requested_profile_id"],
        final_profile_id=row["final_profile_id"],
        provider=row["provider"],
        model=row["model"],
        status=row["status"],
        error_code=row["error_code"],
        safe_error=row["safe_error"],
        allow_fallback=bool(row["allow_fallback"]),
        allow_repair=bool(row["allow_repair"]),
        attempt_count=row["attempt_count"],
        repair_count=row["repair_count"],
        fallback_count=row["fallback_count"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        duration_ms=row["duration_ms"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        attempts=attempts,
    )


class GenerationRunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, create: GenerationRunCreate) -> GenerationRun:
        self.connection.execute(
            """
            INSERT INTO generation_runs (
                id, project_id, use_case, prompt_id, prompt_version, schema_name,
                schema_version, requested_profile_id, status, allow_fallback,
                allow_repair, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)
            """,
            (
                create.id,
                create.project_id,
                create.use_case,
                create.prompt_id,
                create.prompt_version,
                create.schema_name,
                create.schema_version,
                create.requested_profile_id,
                int(create.allow_fallback),
                int(create.allow_repair),
                create.created_at,
            ),
        )
        run = self.get(create.project_id, create.id)
        if run is None:
            raise RuntimeError("Generation run was not created.")
        return run

    def add_attempt(self, run_id: str, create: GenerationAttemptCreate) -> GenerationAttempt:
        attempt_id = f"generation-attempt-{uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO generation_attempts (
                id, project_id, run_id, attempt_index, attempt_kind, profile_id, provider,
                model, status, error_code, retryable, duration_ms, finish_reason,
                input_tokens, output_tokens, created_at
            ) VALUES (?, (SELECT project_id FROM generation_runs WHERE id = ?), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                run_id,
                run_id,
                create.attempt_index,
                create.attempt_kind,
                create.profile_id,
                create.provider,
                create.model,
                create.status,
                create.error_code,
                int(create.retryable),
                create.duration_ms,
                create.finish_reason,
                create.input_tokens,
                create.output_tokens,
                create.created_at,
            ),
        )
        row = self.connection.execute(
            f"{ATTEMPT_COLUMNS} WHERE id = ?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Generation attempt was not created.")
        return _attempt_from_row(row)

    def finish(self, run_id: str, update: GenerationRunUpdate) -> None:
        self.connection.execute(
            """
            UPDATE generation_runs
            SET final_profile_id = ?, provider = ?, model = ?, status = ?,
                error_code = ?, safe_error = ?, attempt_count = ?,
                repair_count = ?, fallback_count = ?, input_tokens = ?,
                output_tokens = ?, duration_ms = ?, completed_at = ?
            WHERE id = ?
            """,
            (
                update.final_profile_id,
                update.provider,
                update.model,
                update.status,
                update.error_code,
                update.safe_error,
                update.attempt_count,
                update.repair_count,
                update.fallback_count,
                update.input_tokens,
                update.output_tokens,
                update.duration_ms,
                update.completed_at,
                run_id,
            ),
        )

    def get(self, project_id: str, run_id: str) -> GenerationRun | None:
        row = self.connection.execute(
            f"{RUN_COLUMNS} WHERE project_id = ? AND id = ?",
            (project_id, run_id),
        ).fetchone()
        if row is None:
            return None
        attempt_rows = self.connection.execute(
            f"{ATTEMPT_COLUMNS} WHERE run_id = ? ORDER BY attempt_index",
            (run_id,),
        ).fetchall()
        return _run_from_row(row, [_attempt_from_row(item) for item in attempt_rows])

    def list(self, project_id: str, limit: int = 100) -> list[GenerationRun]:
        rows = self.connection.execute(
            f"{RUN_COLUMNS} WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [_run_from_row(row, []) for row in rows]


def generation_run_from_row(row: sqlite3.Row) -> GenerationRun:
    return _run_from_row(row, [])


generation_attempt_from_row = _attempt_from_row
