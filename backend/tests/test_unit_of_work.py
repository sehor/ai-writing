"""P2-03 tests: UnitOfWork coordination of the split data store.

Covers (a) cross-repository commits, (b) rollback of every write when a
flow raises mid-unit-of-work, (c) the accept_manuscript_proposal facade
path still creating revision + pending outbox jobs atomically, and
(d) AI_WRITING_DATA_ROOT handling in app.config.resolve_data_root.
"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from app.config import BACKEND_ROOT, resolve_data_root
from app.data import SQLiteWritingDataStore
from app.data.unit_of_work import SqliteUnitOfWork
from app.models import (
    CanonEntityCreate,
    ManuscriptProposalCreate,
    MemoryRecordCreate,
    ProjectCreate,
    SceneContractCreate,
)


def _canon_create(name: str = "Mira") -> CanonEntityCreate:
    return CanonEntityCreate(
        entity_type="character",
        name=name,
        summary="cartographer",
        current_state="healthy",
        constraints="afraid of water",
        last_seen="chapter 1",
        timeline_notes="",
    )


class UnitOfWorkTransactionTests(unittest.TestCase):
    def _store(self, temp_dir: str) -> SQLiteWritingDataStore:
        store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
        store.init()
        return store

    def test_writes_across_two_repositories_commit_together(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            with SqliteUnitOfWork(store.database_path) as uow:
                # Both repositories share the unit of work's single connection.
                self.assertIs(uow.projects.connection, uow.canon.connection)
                project = uow.projects.create(
                    ProjectCreate(title="Shared Fate", premise="One commit.")
                )
                entity = uow.canon.create(project.id, _canon_create())

            # A fresh unit of work sees both writes after the commit.
            self.assertIsNotNone(store.get_project(project.id))
            entities = store.list_canon_entities(project.id)
            self.assertEqual([item.id for item in entities], [entity.id])

    def test_exception_mid_unit_of_work_rolls_back_both_writes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            project = store.create_project(
                ProjectCreate(title="Fragile Draft", premise="All or nothing.")
            )
            with self.assertRaises(RuntimeError):
                with SqliteUnitOfWork(store.database_path) as uow:
                    uow.canon.create(project.id, _canon_create())
                    uow.memory.create(
                        project.id,
                        MemoryRecordCreate(
                            record_type="style_rule",
                            title="voice",
                            scope="global",
                            content="keep it dry",
                            tags="",
                            source_ref="",
                        ),
                    )
                    raise RuntimeError("boom")

            self.assertEqual(store.list_canon_entities(project.id), [])
            self.assertEqual(store.list_memory_records(project.id), [])

    def test_explicit_commit_then_failure_keeps_committed_rows_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = self._store(temp_dir)
            project = store.create_project(
                ProjectCreate(title="Checkpointed", premise="Phase by phase.")
            )
            with self.assertRaises(RuntimeError):
                with SqliteUnitOfWork(store.database_path) as uow:
                    entity = uow.canon.create(project.id, _canon_create())
                    uow.commit()
                    uow.canon.create(project.id, _canon_create(name="Second"))
                    raise RuntimeError("boom")

            names = [item.name for item in store.list_canon_entities(project.id)]
            self.assertEqual(names, [entity.name])


class AcceptManuscriptProposalAtomicityTests(unittest.TestCase):
    def _prepare_pending_proposal(self, store: SQLiteWritingDataStore) -> tuple[str, str]:
        project = store.create_project(
            ProjectCreate(title="Acceptance Flow", premise="Jobs ride along.")
        )
        scene = store.create_scene_contract(
            project.id,
            SceneContractCreate(
                chapter_id="",
                sequence=1,
                title="Archive Threshold",
                pov="Mira",
                goal="Enter the archive.",
                conflict="The map refuses the door.",
                turning_point="The map redraws itself.",
                required_canon="Mira",
                forbidden_facts="the archive burned down",
                open_threads="",
                source_artifact_step=8,
            ),
        )
        proposal = store.create_manuscript_proposal(
            project.id,
            ManuscriptProposalCreate(scene_id=scene.id, title="Draft 1", content="prose"),
        )
        return project.id, proposal.id

    def test_accept_creates_revision_and_pending_outbox_jobs_together(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project_id, proposal_id = self._prepare_pending_proposal(store)

            accepted = store.accept_manuscript_proposal(project_id, proposal_id)

            self.assertIsNotNone(accepted)
            revisions = store.list_manuscript_revisions(project_id)
            self.assertEqual(len(revisions), 1)
            self.assertEqual(accepted.version, 1)

            jobs = store.list_outbox_jobs(project_id)
            self.assertEqual(
                sorted(job.job_type for job in jobs),
                [
                    "clp_extraction",
                    "consistency_analysis",
                    "llm_wiki_ingest",
                    "writeback_analysis",
                ],
            )
            self.assertTrue(all(job.status == "pending" for job in jobs))
            self.assertTrue(all(job.aggregate_id == revisions[0].id for job in jobs))

            # Re-accepting stays idempotent: no second revision or job batch.
            replayed = store.accept_manuscript_proposal(project_id, proposal_id)
            self.assertEqual(replayed.id, accepted.id)
            self.assertEqual(len(store.list_manuscript_revisions(project_id)), 1)
            self.assertEqual(len(store.list_outbox_jobs(project_id)), 4)

    def test_failure_during_job_enqueue_rolls_back_the_whole_acceptance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project_id, proposal_id = self._prepare_pending_proposal(store)

            with mock.patch(
                "app.data.transactions.revision_jobs.enqueue_manuscript_revision_analysis_jobs",
                side_effect=RuntimeError("outbox down"),
            ):
                with self.assertRaises(RuntimeError):
                    store.accept_manuscript_proposal(project_id, proposal_id)

            # Nothing from the failed acceptance survived: no scene upsert,
            # no revision, no index job, proposal still pending review.
            self.assertEqual(store.list_manuscript_scenes(project_id), [])
            self.assertEqual(store.list_manuscript_revisions(project_id), [])
            self.assertEqual(store.list_outbox_jobs(project_id), [])
            proposal = store.get_manuscript_proposal(project_id, proposal_id)
            self.assertEqual(proposal.status, "pending_review")


class ResolveDataRootTests(unittest.TestCase):
    def test_env_var_overrides_data_root(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with mock.patch.dict(os.environ, {"AI_WRITING_DATA_ROOT": temp_dir}):
                self.assertEqual(resolve_data_root(), Path(temp_dir).resolve())

    def test_default_stays_backend_data_directory(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "AI_WRITING_DATA_ROOT"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_data_root(), BACKEND_ROOT / "data")


if __name__ == "__main__":
    unittest.main()
