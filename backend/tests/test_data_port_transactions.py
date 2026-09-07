import ast
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import importlib
import inspect
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.cognition.snapshots import build_project_snapshot
from app.data import SQLiteWritingDataStore
from app.data.ports.manuscript import ManuscriptDataPort
from app.data.ports.reading import ProjectSnapshotReader
from app.data.unit_of_work import SqliteUnitOfWork
from app.models import (
    CanonEntityCreate,
    ManuscriptProposalCreate,
    ProjectCreate,
    SceneContractCreate,
    WritebackProposalCreate,
)
from app.narrative import NarrativeSnapshot


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def methods_of(port):
    return {
        name for name in dir(port) if not name.startswith("_") and callable(getattr(port, name))
    }


class RestrictedPort:
    """A test adapter exposing only the declared protocol, with no facade escape hatch."""

    def __init__(self, store, port):
        self._operations = {name: getattr(store, name) for name in methods_of(port)}

    def __getattr__(self, name):
        if name not in self._operations:
            raise AssertionError(f"Undeclared data operation: {name}")
        return self._operations[name]


class DataPortTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteWritingDataStore(Path(self.temp.name) / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Transactions", premise="One writer.")
        )
        self.scene = self.store.create_scene_contract(
            self.project.id, SceneContractCreate(sequence=1, title="Arrival", pov="Mira")
        )

    def accept_manuscript(self):
        proposal = self.store.create_manuscript_proposal(
            self.project.id,
            ManuscriptProposalCreate(
                scene_id=self.scene.id, title="Arrival", content="Mira arrives."
            ),
        )
        self.store.accept_manuscript_proposal(self.project.id, proposal.id)
        return self.store.list_manuscript_revisions(self.project.id)[0]

    def writeback(self):
        return self.store.create_writeback_proposal(
            self.project.id,
            WritebackProposalCreate(
                target="canon_entity",
                title="Mira",
                payload=CanonEntityCreate(entity_type="character", name="Mira").model_dump(),
            ),
        )

    def test_write_unit_of_work_reserves_before_any_repository_read(self):
        with SqliteUnitOfWork(self.store.database_path, write=True) as uow:
            self.assertTrue(uow.connection.in_transaction)
            with closing(sqlite3.connect(self.store.database_path, timeout=0)) as competitor:
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    competitor.execute("BEGIN IMMEDIATE")
        with closing(sqlite3.connect(self.store.database_path, timeout=0)) as competitor:
            competitor.execute("BEGIN IMMEDIATE")

    def test_two_restores_get_distinct_versions_and_complete_job_batches(self):
        original = self.accept_manuscript()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.store.restore_manuscript_revision, self.project.id, original.id)
                for _ in range(2)
            ]
            restored = [future.result() for future in futures]
        self.assertEqual(sorted(scene.version for scene in restored), [2, 3])
        self.assertEqual(len(self.store.list_manuscript_revisions(self.project.id)), 3)
        self.assertEqual(len(self.store.list_outbox_jobs(self.project.id)), 12)

    def test_concurrent_writeback_acceptance_is_idempotent(self):
        proposal = self.writeback()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.store.accept_writeback_proposal, self.project.id, proposal.id)
                for _ in range(2)
            ]
            accepted = [future.result() for future in futures]
        self.assertEqual(accepted[0], accepted[1])
        self.assertEqual(accepted[0].status, "accepted")
        self.assertEqual(len(self.store.list_canon_entities(self.project.id)), 1)

    def test_restore_failure_rolls_back_scene_revision_and_jobs(self):
        original = self.accept_manuscript()
        before = (
            self.store.list_manuscript_scenes(self.project.id),
            self.store.list_manuscript_revisions(self.project.id),
            self.store.list_outbox_jobs(self.project.id),
        )
        with patch(
            "app.data.transactions.revision_jobs.enqueue_manuscript_revision_analysis_jobs",
            side_effect=RuntimeError("outbox failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.store.restore_manuscript_revision(self.project.id, original.id)
        after = (
            self.store.list_manuscript_scenes(self.project.id),
            self.store.list_manuscript_revisions(self.project.id),
            self.store.list_outbox_jobs(self.project.id),
        )
        self.assertEqual(after, before)

    def test_writeback_failure_rolls_back_target_and_review(self):
        proposal = self.writeback()
        with patch(
            "app.data.repositories.review.ReviewRepository.mark_writeback_accepted",
            side_effect=RuntimeError("review failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.store.accept_writeback_proposal(self.project.id, proposal.id)
        self.assertEqual(self.store.list_canon_entities(self.project.id), [])
        self.assertEqual(self.store.get_writeback_proposal(self.project.id, proposal.id), proposal)

    def test_snapshots_work_through_only_the_declared_operations(self):
        project = build_project_snapshot(
            self.project.id, RestrictedPort(self.store, ProjectSnapshotReader)
        )
        self.assertEqual(project.project.id, self.project.id)
        snapshot = NarrativeSnapshot.for_scene(
            project_id=self.project.id,
            scene_id=self.scene.id,
            data_store=RestrictedPort(self.store, ManuscriptDataPort),
        )
        self.assertEqual(snapshot.scene.id, self.scene.id)

    def test_port_signatures_match_facade_and_services_cannot_use_whole_store(self):
        for path in (APP_ROOT / "data" / "ports").glob("*.py"):
            module = importlib.import_module(f"app.data.ports.{path.stem}")
            for port in vars(module).values():
                if not isinstance(port, type) or port.__module__ != module.__name__:
                    continue
                for name in methods_of(port):
                    declaration = inspect.signature(getattr(port, name))
                    implementation = inspect.signature(getattr(SQLiteWritingDataStore, name))
                    # Annotations can use more precise output types; call shape must match.
                    self.assertEqual(
                        [(p.name, p.kind, p.default) for p in declaration.parameters.values()],
                        [(p.name, p.kind, p.default) for p in implementation.parameters.values()],
                        f"{port.__name__}.{name}",
                    )
        for path in (APP_ROOT / "services").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotEqual(node.id, "WritingDataStore", path.name)

    def test_flows_never_own_commit_or_open_connections(self):
        for path in (APP_ROOT / "data" / "transactions").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, {"commit", "rollback", "connect"}, path.name)
