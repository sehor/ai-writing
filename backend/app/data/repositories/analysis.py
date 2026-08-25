"""Analysis repository: idempotent analysis runs (P1-04).

One row per (project_id, source_ref, processor, input_hash). Repeating
an unchanged request replays the stored result instead of generating
duplicate proposals. An explicit re-run bumps run_version on the same
row; a failed run is retried on the next request.
"""

import json
import sqlite3

from app.analysis.models import AnalysisRun
from app.data.helpers import make_record_id, utc_now

ANALYSIS_RUN_COLUMNS = """
    SELECT id, project_id, source_ref, processor, input_hash, status,
           result_json, run_version, created_at, completed_at
    FROM analysis_runs
"""


def analysis_run_from_row(row: sqlite3.Row) -> AnalysisRun:
    return AnalysisRun(
        id=row["id"],
        project_id=row["project_id"],
        source_ref=row["source_ref"],
        processor=row["processor"],
        input_hash=row["input_hash"],
        status=row["status"],
        result_json=json.loads(row["result_json"]),
        run_version=row["run_version"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


class AnalysisRepository:
    """SQL for the analysis_runs table, bound to one connection."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get(
        self,
        project_id: str,
        source_ref: str,
        processor: str,
        input_hash: str | None = None,
    ) -> AnalysisRun | None:
        """Latest run for a source/processor pair.

        Without input_hash the newest run of any input is returned;
        with it, only the run matching that exact input matches.
        """
        query = f"{ANALYSIS_RUN_COLUMNS} WHERE project_id = ? AND source_ref = ? AND processor = ?"
        params: list[object] = [project_id, source_ref, processor]
        if input_hash is not None:
            query += " AND input_hash = ?"
            params.append(input_hash)
        query += " ORDER BY created_at DESC, run_version DESC LIMIT 1"
        row = self.connection.execute(query, params).fetchone()
        return analysis_run_from_row(row) if row else None

    def list_runs(self, project_id: str, limit: int = 100) -> list[AnalysisRun]:
        rows = self.connection.execute(
            f"""
            {ANALYSIS_RUN_COLUMNS}
            WHERE project_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
        return [analysis_run_from_row(row) for row in rows]

    def record(
        self,
        *,
        project_id: str,
        source_ref: str,
        processor: str,
        input_hash: str,
        status: str,
        result_json: dict,
    ) -> AnalysisRun:
        """Insert or replace the run inside the caller's transaction.

        Same input key -> the existing row is updated in place and its
        run_version increments, so explicit re-runs keep one lineage per
        input instead of stacking duplicate rows.
        """
        now = utc_now()
        existing = self.connection.execute(
            """
            SELECT id, run_version FROM analysis_runs
            WHERE project_id = ? AND source_ref = ? AND processor = ? AND input_hash = ?
            """,
            (project_id, source_ref, processor, input_hash),
        ).fetchone()
        if existing is not None:
            self.connection.execute(
                """
                UPDATE analysis_runs
                SET status = ?,
                    result_json = ?,
                    run_version = run_version + 1,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result_json, ensure_ascii=False),
                    now,
                    existing["id"],
                ),
            )
            row = self.connection.execute(
                f"{ANALYSIS_RUN_COLUMNS} WHERE id = ?",
                (existing["id"],),
            ).fetchone()
            return analysis_run_from_row(row)

        run_id = make_record_id(
            f"analysis-{processor}-{source_ref}",
            {
                row["id"]
                for row in self.connection.execute("SELECT id FROM analysis_runs").fetchall()
            },
        )
        self.connection.execute(
            """
            INSERT INTO analysis_runs (
                id, project_id, source_ref, processor, input_hash, status,
                result_json, run_version, created_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                run_id,
                project_id,
                source_ref,
                processor,
                input_hash,
                status,
                json.dumps(result_json, ensure_ascii=False),
                now,
                now,
            ),
        )
        row = self.connection.execute(
            f"{ANALYSIS_RUN_COLUMNS} WHERE id = ?",
            (run_id,),
        ).fetchone()
        return analysis_run_from_row(row)
