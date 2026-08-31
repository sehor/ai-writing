from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.data import get_data_store
from app.main import app
from app.models import ManuscriptSceneUpdate, ProjectCreate
from app.outbox.dispatcher import get_outbox_dispatcher
import test_manuscript_editing


class ManuscriptConflictTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store, self.project_id, self.scene_id = (
            test_manuscript_editing.ManuscriptEditingTests()._seed_accepted_scene(temp.name)
        )
        self.dispatcher = Mock()
        app.dependency_overrides[get_data_store] = lambda: self.store
        app.dependency_overrides[get_outbox_dispatcher] = lambda: self.dispatcher
        self.addCleanup(app.dependency_overrides.clear)
        # Keep the dispatcher stopped so transaction effects can be inspected.
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = f"/api/projects/{self.project_id}/manuscript/scenes/{self.scene_id}"

    def body(self, version=1, content="Window A edit"):
        return {"title": "Edited", "content": content, "expected_scene_version": version}

    def state(self):
        return (
            self.store.get_manuscript_scene(self.project_id, self.scene_id),
            self.store.list_manuscript_revisions(self.project_id),
            self.store.list_outbox_jobs(self.project_id),
        )

    def test_stale_save_is_409_without_revision_jobs_or_dispatch(self):
        first = self.client.put(self.url, json=self.body())
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["version"], 2)
        before = self.state()
        self.dispatcher.reset_mock()
        for version in (1, 9):
            with self.subTest(version=version):
                stale = self.client.put(self.url, json=self.body(version, "Window B edit"))
                self.assertEqual(stale.status_code, 409, stale.text)
                self.assertEqual(self.state(), before)
                self.assertEqual(self.dispatcher.mock_calls, [])
        self.assertEqual(before[0].content, "Window A edit")
        # Explicit review/rebase to the current version allows a normal commit.
        resolved = self.client.put(self.url, json=self.body(2, "A and B merged"))
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["version"], 3)
        self.assertEqual(len(self.state()[1]), 3)
        self.assertEqual(len(self.state()[2]), 12)

    def test_missing_or_invalid_version_cannot_bypass_protection(self):
        before = self.state()
        bodies = [{"title": "Legacy", "content": "Unversioned save"}]
        bodies.extend(self.body(version) for version in (None, 0, -1, True, "1", 1.5))
        for body in bodies:
            with self.subTest(body=body):
                response = self.client.put(self.url, json=body)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.dispatcher.mock_calls, [])

    def test_missing_scene_and_cross_project_stay_404(self):
        other = self.store.create_project(ProjectCreate(title="Other", premise="Isolated"))
        before = self.state()
        for project_id, scene_id in (
            (self.project_id, "missing"),
            (other.id, self.scene_id),
            ("missing", self.scene_id),
        ):
            response = self.client.put(
                f"/api/projects/{project_id}/manuscript/scenes/{scene_id}", json=self.body()
            )
            self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.state(), before)

    def test_two_concurrent_writers_commit_only_one_revision(self):
        barrier = Barrier(2)

        def save(content):
            barrier.wait(timeout=5)
            try:
                return self.store.update_manuscript_scene(
                    self.project_id, self.scene_id, ManuscriptSceneUpdate(**self.body(1, content))
                )
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ["A", "B"]))
        self.assertEqual(sum(result is not None for result in results), 1)
        scene, revisions, jobs = self.state()
        self.assertEqual(scene.version, 2)
        self.assertEqual(len(revisions), 2)
        self.assertEqual(len(jobs), 8)
        self.assertEqual(scene.content, next(result.content for result in results if result))

    def test_failure_after_version_check_rolls_back_all_writes(self):
        before = self.state()
        with patch(
            "app.data.flows.enqueue_committed_revision_jobs", side_effect=RuntimeError("fail")
        ):
            with self.assertRaises(RuntimeError):
                self.store.update_manuscript_scene(
                    self.project_id, self.scene_id, ManuscriptSceneUpdate(**self.body())
                )
        self.assertEqual(self.state(), before)
