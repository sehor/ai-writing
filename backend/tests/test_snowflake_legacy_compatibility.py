from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app


class SnowflakeLegacyCompatibilityTests(unittest.TestCase):
    def test_legacy_save_routes_to_draft_revision_without_writing_projection(self) -> None:
        with TemporaryDirectory() as temp:
            store = SQLiteWritingDataStore(Path(temp) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project = client.post(
                        "/api/projects",
                        json={"title": "Compatibility", "premise": "Keep history."},
                    ).json()
                    saved = client.put(
                        f"/api/projects/{project['id']}/snowflake/artifacts/1",
                        json={"content": "A keeper must preserve a city before dawn."},
                    )
                    self.assertEqual(saved.status_code, 200, saved.text)
                    self.assertEqual(saved.headers.get("deprecation"), "true")
                    self.assertIn("artifact-revisions", saved.headers.get("link", ""))
                    self.assertIsNone(store.get_snowflake_artifact(project["id"], 1))

                    revisions, total = store.list_snowflake_revisions(
                        project["id"], 1, limit=10, offset=0
                    )
                    self.assertEqual(total, 1)
                    self.assertEqual(revisions[0].status, "draft")

                    accepted = client.post(
                        f"/api/projects/{project['id']}/snowflake/artifact-revisions/"
                        f"{revisions[0].id}/decisions",
                        json={"decision": "accepted", "expected_head_revision_id": ""},
                    )
                    self.assertEqual(accepted.status_code, 200, accepted.text)
                    projection = store.get_snowflake_artifact(project["id"], 1)
                    self.assertIsNotNone(projection)
                    self.assertEqual(projection.content, revisions[0].content)
            finally:
                app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
