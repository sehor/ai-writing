from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app


class ReviewLoopRouteTests(unittest.TestCase):
    def test_manuscript_and_writeback_review_loop_through_http_routes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_response = client.post(
                        "/api/projects",
                        json={
                            "title": "Route Loop",
                            "premise": "A cartographer maps a city that resists memory.",
                        },
                    )
                    self.assertEqual(project_response.status_code, 201)
                    project_id = project_response.json()["id"]

                    chapter_response = client.post(
                        f"/api/projects/{project_id}/manuscript/chapters",
                        json={
                            "sequence": 1,
                            "title": "The Locked Map",
                            "summary": "Mira reaches the archive.",
                        },
                    )
                    self.assertEqual(chapter_response.status_code, 201)
                    chapter = chapter_response.json()

                    scene_response = client.post(
                        f"/api/projects/{project_id}/scene-contracts",
                        json={
                            "chapter_id": chapter["id"],
                            "sequence": 1,
                            "title": "Archive Threshold",
                            "pov": "Mira",
                            "goal": "Enter the archive.",
                            "conflict": "The map refuses the door.",
                            "turning_point": "The map redraws itself.",
                            "required_canon": "Mira carries the altered map.",
                            "forbidden_facts": "The patron's identity.",
                            "open_threads": "Who changed the map?",
                            "source_artifact_step": 8,
                        },
                    )
                    self.assertEqual(scene_response.status_code, 201)
                    scene = scene_response.json()

                    proposal_response = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    )
                    self.assertEqual(proposal_response.status_code, 201)
                    proposal = proposal_response.json()
                    self.assertEqual(proposal["status"], "pending_review")

                    accept_response = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status",
                        json={"status": "accepted"},
                    )
                    self.assertEqual(accept_response.status_code, 200)
                    self.assertEqual(accept_response.json()["status"], "accepted")

                    export_response = client.get(f"/api/projects/{project_id}/manuscript/export")
                    self.assertEqual(export_response.status_code, 200)
                    export = export_response.json()
                    self.assertIn("## Chapter 1: The Locked Map", export["content"])
                    self.assertIn("### 1. Archive Threshold", export["content"])

                    writeback_response = client.post(
                        f"/api/projects/{project_id}/writeback/proposals",
                        json={
                            "target": "canon_entity",
                            "action": "create",
                            "title": "Mira has the altered map",
                            "rationale": "Accepted manuscript establishes the map state.",
                            "payload": {
                                "entity_type": "item",
                                "name": "Altered map",
                                "summary": "A map that redraws itself near the archive.",
                                "current_state": "Mira carries it at the archive threshold.",
                                "constraints": "Do not reveal who altered it yet.",
                                "last_seen": "Archive Threshold",
                                "timeline_notes": "Introduced in chapter 1.",
                            },
                            "source_ref": f"manuscript_scene:{scene['id']}",
                        },
                    )
                    self.assertEqual(writeback_response.status_code, 201)
                    writeback = writeback_response.json()

                    applied_response = client.put(
                        f"/api/projects/{project_id}/writeback/proposals/{writeback['id']}/status",
                        json={"status": "accepted"},
                    )
                    self.assertEqual(applied_response.status_code, 200)
                    applied = applied_response.json()
                    self.assertEqual(applied["status"], "accepted")
                    self.assertTrue(applied["applied_record_id"])

                    canon_response = client.get(f"/api/projects/{project_id}/canon/entities")
                    self.assertEqual(canon_response.status_code, 200)
                    self.assertEqual(canon_response.json()[0]["name"], "Altered map")
            finally:
                app.dependency_overrides.clear()

    def test_accepted_manuscript_proposal_is_terminal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id = client.post(
                        "/api/projects",
                        json={
                            "title": "Terminal Proposal",
                            "premise": "A map refuses to be edited twice.",
                        },
                    ).json()["id"]
                    scene = client.post(
                        f"/api/projects/{project_id}/scene-contracts",
                        json={
                            "sequence": 1,
                            "title": "Single Accept",
                            "pov": "Mira",
                            "goal": "Accept one draft.",
                            "conflict": "The review button is clicked twice.",
                            "turning_point": "The second click is ignored.",
                            "required_canon": "",
                            "forbidden_facts": "",
                            "open_threads": "",
                            "source_artifact_step": 8,
                        },
                    ).json()
                    proposal = client.post(
                        f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                    ).json()

                    first_accept = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status",
                        json={"status": "accepted"},
                    )
                    second_accept = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status",
                        json={"status": "accepted"},
                    )
                    reject_after_accept = client.put(
                        f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status",
                        json={"status": "rejected"},
                    )

                    self.assertEqual(first_accept.status_code, 200)
                    self.assertEqual(second_accept.status_code, 200)
                    self.assertEqual(reject_after_accept.status_code, 409)
                    self.assertEqual(len(store.list_manuscript_revisions(project_id)), 1)
                    self.assertEqual(
                        store.get_manuscript_proposal(project_id, proposal["id"]).status,
                        "accepted",
                    )
            finally:
                app.dependency_overrides.clear()

    def test_invalid_deepseek_env_returns_501_for_provider_routes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            env = {
                "DEEPSEEK_API_KEY": "test-key",
                "DEEPSEEK_TEMPERATURE": "not-a-number",
            }
            try:
                with patch.dict("os.environ", env, clear=False):
                    with TestClient(app) as client:
                        project_id = client.post(
                            "/api/projects",
                            json={
                                "title": "Invalid Provider Env",
                                "premise": "Bad runtime config should not become a 500.",
                            },
                        ).json()["id"]
                        scene = client.post(
                            f"/api/projects/{project_id}/scene-contracts",
                            json={
                                "sequence": 1,
                                "title": "Provider Config",
                                "pov": "Mira",
                                "goal": "Reach provider route setup.",
                                "conflict": "The env is invalid.",
                                "turning_point": "The route rejects config.",
                                "required_canon": "",
                                "forbidden_facts": "",
                                "open_threads": "",
                                "source_artifact_step": 8,
                            },
                        ).json()
                        proposal = client.post(
                            f"/api/projects/{project_id}/manuscript/proposals/from-scene/{scene['id']}"
                        ).json()
                        client.put(
                            f"/api/projects/{project_id}/manuscript/proposals/{proposal['id']}/status",
                            json={"status": "accepted"},
                        )
                        revision_id = store.list_manuscript_revisions(project_id)[0].id

                        reference_response = client.post(
                            f"/api/projects/{project_id}/references/suggestions/generate/provider",
                            json={
                                "suggestion_type": "scene_bridge",
                                "scope_type": "project",
                                "scope_ref": "",
                                "author_problem": "Need a bridge.",
                                "desired_output": "",
                            },
                        )
                        writeback_response = client.post(
                            f"/api/projects/{project_id}/writeback/proposals/from-revision/{revision_id}/provider"
                        )

                    self.assertEqual(reference_response.status_code, 501)
                    self.assertEqual(writeback_response.status_code, 501)
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
