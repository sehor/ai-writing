from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import ManuscriptProposalCreate


class ManuscriptPreAcceptConsistencyTests(unittest.TestCase):
    def test_critical_finding_is_visible_and_blocks_acceptance(self) -> None:
        with TemporaryDirectory() as temp:
            store = SQLiteWritingDataStore(Path(temp) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project = client.post(
                        "/api/projects",
                        json={"title": "Consistency Gate", "premise": "Keep the secret."},
                    ).json()
                    scene = client.post(
                        f"/api/projects/{project['id']}/scene-contracts",
                        json={
                            "sequence": 1,
                            "title": "The locked room",
                            "pov": "Mira",
                            "goal": "Open the door",
                            "conflict": "The key is missing",
                            "turning_point": "The wall answers",
                            "outcome": "Mira remains trapped",
                            "forbidden_facts": "the king is alive",
                        },
                    ).json()
                    proposal = client.post(
                        f"/api/projects/{project['id']}/manuscript/proposals/from-scene/{scene['id']}"
                    ).json()
                    draft = {
                        "title": proposal["title"],
                        "content": "Mira whispers that the king is alive.",
                        "expected_scene_version": 0,
                    }
                    preview = client.post(
                        f"/api/projects/{project['id']}/manuscript/proposals/{proposal['id']}/consistency",
                        json=draft,
                    )
                    self.assertEqual(preview.status_code, 200, preview.text)
                    self.assertEqual(preview.json()["summary"]["critical_count"], 1)

                    blocked = client.post(
                        f"/api/projects/{project['id']}/manuscript/proposals/{proposal['id']}/accept",
                        json=draft,
                    )
                    self.assertEqual(blocked.status_code, 422, blocked.text)

                    critical_proposal = store.create_manuscript_proposal(
                        project["id"],
                        ManuscriptProposalCreate(
                            scene_id=scene["id"],
                            title="Critical legacy-route proposal",
                            content="Mira whispers that the king is alive.",
                        ),
                    )
                    legacy_bypass = client.put(
                        f"/api/projects/{project['id']}/manuscript/proposals/{critical_proposal.id}/status",
                        json={"status": "accepted"},
                    )
                    self.assertEqual(legacy_bypass.status_code, 422, legacy_bypass.text)
                    self.assertEqual(legacy_bypass.headers.get("deprecation"), "true")
                    self.assertIn("/accept", legacy_bypass.headers.get("link", ""))
                    self.assertEqual(store.list_manuscript_revisions(project["id"]), [])
                    self.assertEqual(
                        store.get_manuscript_proposal(project["id"], proposal["id"]).status,
                        "pending_review",
                    )
                    self.assertEqual(
                        store.get_manuscript_proposal(project["id"], critical_proposal.id).status,
                        "pending_review",
                    )
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
