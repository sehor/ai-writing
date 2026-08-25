from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import ProjectCreate, SceneContractCreate
from app.review.state_machine import (
    InvalidReviewTransitionError,
    is_terminal_review_status,
    validate_review_transition,
)


class ReviewStateMachineUnitTests(unittest.TestCase):
    def test_pending_review_can_move_to_any_decision(self) -> None:
        for target in ("accepted", "rejected", "superseded"):
            validate_review_transition("pending_review", target)

    def test_decided_states_are_terminal(self) -> None:
        for current in ("accepted", "rejected", "superseded"):
            self.assertTrue(is_terminal_review_status(current))
            for target in ("pending_review", "accepted", "rejected", "superseded"):
                if current == target:
                    continue
                with self.assertRaises(InvalidReviewTransitionError):
                    validate_review_transition(current, target)

    def test_repeating_the_current_status_is_an_idempotent_no_op(self) -> None:
        for status in ("pending_review", "accepted", "rejected", "superseded"):
            validate_review_transition(status, status)

    def test_error_names_subject_and_states(self) -> None:
        with self.assertRaises(InvalidReviewTransitionError) as ctx:
            validate_review_transition("accepted", "rejected", "Write-back proposal")
        self.assertIn("Write-back proposal", str(ctx.exception))
        self.assertIn("accepted", str(ctx.exception))
        self.assertIn("rejected", str(ctx.exception))


class ManuscriptProposalTransitionRouteTests(unittest.TestCase):
    def _project_with_scene(self, client: TestClient, title: str) -> tuple[str, dict]:
        project_id = client.post(
            "/api/projects",
            json={"title": title, "premise": "A review state machine test."},
        ).json()["id"]
        scene = client.post(
            f"/api/projects/{project_id}/scene-contracts",
            json={
                "sequence": 1,
                "title": "State Machine",
                "pov": "Mira",
                "goal": "Accept exactly once.",
                "conflict": "Repeated clicks.",
                "turning_point": "The machine refuses.",
                "source_artifact_step": 8,
            },
        ).json()
        return project_id, scene

    def test_accepted_manuscript_proposal_rejects_all_reverse_moves(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, scene = self._project_with_scene(client, "Reverse Moves")
                    proposal = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    ).json()
                    url = f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status"
                    self.assertEqual(client.put(url, json={"status": "accepted"}).status_code, 200)
                    self.assertEqual(client.put(url, json={"status": "rejected"}).status_code, 409)
                    self.assertEqual(
                        client.put(url, json={"status": "pending_review"}).status_code,
                        409,
                    )
                    # Idempotent repeat stays a success without side effects.
                    self.assertEqual(client.put(url, json={"status": "accepted"}).status_code, 200)

                    missing = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/nope/status",
                        json={"status": "accepted"},
                    )
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(missing.status_code, 404)

    def test_accepting_one_proposal_supersedes_pending_siblings_of_the_scene(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, scene = self._project_with_scene(client, "Supersede")
                    first = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    ).json()
                    second = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    ).json()
                    self.assertNotEqual(first["id"], second["id"])

                    accepted = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{first['id']}/status",
                        json={"status": "accepted"},
                    )
                    self.assertEqual(accepted.status_code, 200)

                    statuses = {
                        proposal["id"]: proposal["status"]
                        for proposal in client.get(
                            f"/api/projects/{project_id}/manuscript/proposals"
                        ).json()
                    }
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(statuses[first["id"]], "accepted")
        self.assertEqual(statuses[second["id"]], "superseded")

    def test_superseded_scene_proposal_cannot_be_accepted_afterwards(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, scene = self._project_with_scene(client, "Late Accept")
                    first = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    ).json()
                    second = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    ).json()
                    client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{first['id']}/status",
                        json={"status": "accepted"},
                    )
                    late = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{second['id']}/status",
                        json={"status": "accepted"},
                    )
                    revisions = client.get(
                        f"/api/projects/{project_id}/manuscript/revisions"
                    ).json()
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(late.status_code, 409)
        self.assertEqual(len(revisions), 1)


class ReferenceSuggestionTransitionTests(unittest.TestCase):
    def test_reference_suggestion_follows_the_shared_state_machine(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id = client.post(
                        "/api/projects",
                        json={
                            "title": "Reference Flow",
                            "premise": "Suggestions obey the machine.",
                        },
                    ).json()["id"]
                    suggestion = client.post(
                        f"/api/projects/{project_id}/references/suggestions/generate",
                        json={
                            "suggestion_type": "brainstorm",
                            "scope_type": "project",
                            "author_problem": "What if the map lies?",
                        },
                    ).json()
                    url = (
                        f"/api/projects/{project_id}/references/suggestions/"
                        f"{suggestion['id']}/status"
                    )
                    accepted = client.put(url, json={"status": "accepted"})
                    reverse = client.put(url, json={"status": "rejected"})
                    pending_again = client.put(url, json={"status": "pending_review"})

                    fresh = client.post(
                        f"/api/projects/{project_id}/references/suggestions/generate",
                        json={
                            "suggestion_type": "canon_gap",
                            "scope_type": "project",
                            "author_problem": "Who guards the archive?",
                        },
                    ).json()
                    manual_super = client.put(
                        f"/api/projects/{project_id}/references/suggestions/{fresh['id']}/status",
                        json={"status": "superseded"},
                    )
                    after_super = client.put(
                        f"/api/projects/{project_id}/references/suggestions/{fresh['id']}/status",
                        json={"status": "accepted"},
                    )
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(reverse.status_code, 409)
        self.assertEqual(pending_again.status_code, 409)
        self.assertEqual(manual_super.status_code, 200)
        self.assertEqual(after_super.status_code, 409)

    def test_reference_suggestion_store_create_uses_pending_review(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Ref", premise="P."))
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=1, title="Scene One"),
            )
            self.assertTrue(scene.id)


if __name__ == "__main__":
    unittest.main()
