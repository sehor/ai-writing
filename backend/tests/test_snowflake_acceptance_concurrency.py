from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from app.data import SQLiteWritingDataStore
from app.data.flows import SnowflakeHeadConflictError
from app.data.repositories.outbox import OutboxRepository
from app.data.repositories.snowflake import SnowflakeRepository
from app.data.repositories.snowflake_records import SnowflakeRecordRepository
from app.models import ProjectCreate, SnowflakeArtifactRevisionCreate, SnowflakeRecordRevisionCreate


class SnowflakeAcceptanceConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "app.db"
        self.store = SQLiteWritingDataStore(self.path)
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Concurrent review", premise="A mapmaker saves a city.")
        )

    def candidate(self, kind, text):
        if kind == "artifact":
            return self.store.create_snowflake_revision(
                self.project.id, SnowflakeArtifactRevisionCreate(step_number=1, content=text)
            )
        return self.store.create_snowflake_record_revision(
            self.project.id,
            SnowflakeRecordRevisionCreate(
                step_number=6,
                record_id="opening",
                position=1,
                payload={
                    "record_id": "opening",
                    "act": "I",
                    "section": "Opening",
                    "sequence": 1,
                    "synopsis": text,
                    "step4_paragraph_refs": ["setup"],
                    "character_refs": ["protagonist"],
                },
            ),
        )

    def accept(self, store, kind, revision):
        if kind == "artifact":
            return store.decide_snowflake_revision(
                project_id=self.project.id,
                revision_id=revision.id,
                decision="accepted",
                expected_head_revision_id="",
            )
        return store.decide_snowflake_record_revision(
            self.project.id, revision.id, decision="accepted", expected_revision_id=""
        )

    def dump(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return list(connection.iterdump())

    def test_independent_connections_allow_only_one_competing_acceptance(self):
        for kind in ("artifact", "record"):
            with self.subTest(kind=kind):
                candidates = [self.candidate(kind, f"Candidate {n}") for n in (1, 2)]
                start = Barrier(2)
                unprotected_read = Barrier(2)
                repository = (
                    SnowflakeRepository if kind == "artifact" else SnowflakeRecordRepository
                )
                get_head = repository.get_head

                def synchronized_head(repo, *args):
                    head = get_head(repo, *args)
                    # Reproduce the old read/read/write/write race only when no write
                    # transaction protects the read. Never wait behind a writer lock.
                    if not repo.connection.in_transaction:
                        unprotected_read.wait(timeout=5)
                    return head

                def contender(revision):
                    other = SQLiteWritingDataStore(self.path)
                    start.wait(timeout=5)
                    try:
                        self.accept(other, kind, revision)
                        return "accepted", revision
                    except (SnowflakeHeadConflictError, ValueError) as error:
                        self.assertIn("changed", str(error))
                        return "conflict", revision

                with patch.object(repository, "get_head", synchronized_head):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(contender, candidates))
                self.assertEqual(sorted(status for status, _ in results), ["accepted", "conflict"])
                loser = next(revision for status, revision in results if status == "conflict")
                getter = (
                    self.store.get_snowflake_revision
                    if kind == "artifact"
                    else self.store.get_snowflake_record_revision
                )
                self.assertEqual(getter(self.project.id, loser.id).status, "draft")

    def test_outbox_failure_rolls_back_every_acceptance_write(self):
        for kind in ("artifact", "record"):
            with self.subTest(kind=kind):
                candidate = self.candidate(kind, "Rollback candidate")
                before = self.dump()
                with patch.object(
                    OutboxRepository, "insert", side_effect=RuntimeError("outbox failure")
                ):
                    with self.assertRaisesRegex(RuntimeError, "outbox failure"):
                        self.accept(self.store, kind, candidate)
                self.assertEqual(self.dump(), before)

    def test_accepting_same_candidate_again_has_no_side_effects(self):
        for kind in ("artifact", "record"):
            with self.subTest(kind=kind):
                candidate = self.candidate(kind, "Idempotent candidate")
                self.accept(self.store, kind, candidate)
                before = self.dump()
                self.accept(SQLiteWritingDataStore(self.path), kind, candidate)
                self.assertEqual(self.dump(), before)
