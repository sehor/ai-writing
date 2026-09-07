from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import ProjectCreate, SceneContractCreate


def seed_legacy_revision(store: SQLiteWritingDataStore, project_id: str, content: str) -> str:
    revision_id = f"legacy-step-10:{project_id}"
    with store.connect() as connection:
        connection.execute(
            """
            INSERT INTO snowflake_artifact_revisions (
                id, project_id, step_number, artifact_type, revision_no,
                source, status, content, created_at
            ) VALUES (?, ?, 10, 'manuscript', 1, 'legacy', 'legacy_draft', ?, ?)
            """,
            (revision_id, project_id, content, "2026-09-03T00:00:00+00:00"),
        )
    return revision_id


class LegacyManuscriptImportTests(unittest.TestCase):
    def test_human_selection_becomes_pending_proposal_before_regular_acceptance(self) -> None:
        with TemporaryDirectory() as temp:
            store = SQLiteWritingDataStore(Path(temp) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project = client.post(
                        "/api/projects",
                        json={"title": "Legacy Import", "premise": "Recover the old draft."},
                    ).json()
                    scene = client.post(
                        f"/api/projects/{project['id']}/scene-contracts",
                        json={
                            "sequence": 1,
                            "title": "Recovered scene",
                            "pov": "Mira",
                            "goal": "Open the archive",
                            "conflict": "The lock resists",
                            "turning_point": "The map changes",
                            "outcome": "The door opens",
                        },
                    ).json()
                    legacy_id = seed_legacy_revision(
                        store,
                        project["id"],
                        "Opening material.\n\nSelected scene prose.\n\nClosing material.",
                    )

                    imported = client.post(
                        f"/api/projects/{project['id']}/manuscript/proposals/from-legacy-snowflake/{legacy_id}",
                        json={
                            "scene_id": scene["id"],
                            "title": "Recovered scene",
                            "content": "Selected scene prose.",
                        },
                    )
                    self.assertEqual(imported.status_code, 201, imported.text)
                    proposal = imported.json()
                    self.assertEqual(proposal["source"], "legacy_snowflake_import")
                    self.assertEqual(proposal["status"], "pending_review")
                    self.assertEqual(store.list_manuscript_revisions(project["id"]), [])

                    accepted = client.post(
                        f"/api/projects/{project['id']}/manuscript/proposals/{proposal['id']}/accept",
                        json={
                            "title": proposal["title"],
                            "content": proposal["content"],
                            "expected_scene_version": 0,
                        },
                    )
                    self.assertEqual(accepted.status_code, 200, accepted.text)
                    self.assertEqual(len(store.list_manuscript_revisions(project["id"])), 1)
            finally:
                app.dependency_overrides.clear()

    def test_import_rejects_content_that_is_not_an_exact_human_selection(self) -> None:
        with TemporaryDirectory() as temp:
            store = SQLiteWritingDataStore(Path(temp) / "app.db")
            store.init()
            project = store.create_project(
                ProjectCreate(title="Legacy Import", premise="Recover the old draft.")
            )
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=1, title="Recovered scene"),
            )
            legacy_id = seed_legacy_revision(store, project.id, "Only the preserved words.")
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    response = client.post(
                        f"/api/projects/{project.id}/manuscript/proposals/from-legacy-snowflake/{legacy_id}",
                        json={
                            "scene_id": scene.id,
                            "title": "Invented",
                            "content": "Words that were not preserved.",
                        },
                    )
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(store.list_manuscript_proposals(project.id), [])
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
