from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.data.migrations import MIGRATIONS, run_migrations
from app.errors import StateConflictError
from app.http_errors import install_application_error_handlers
from app.models import (
    CharacterKnowledgeCreate,
    KnowledgeStateCorrection,
    NarrativeVersionChange,
    ProjectCreate,
    SceneContractCreate,
    StoryFact,
    StoryFactCorrection,
    StoryFactCreate,
)
from app.narrative import NarrativeSnapshot
from app.routers.narrative import router
from app.services.backup_service import BackupError, ProjectBackupService


class NarrativeMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SQLiteWritingDataStore(self.root / "app.db")
        self.store.init()
        self.project = self.store.create_project(
            ProjectCreate(title="Author corrections", premise="Secrets")
        )
        self.other = self.store.create_project(
            ProjectCreate(title="Other author", premise="Private")
        )
        self.fact = self.store.create_story_fact(
            self.project.id,
            StoryFactCreate(
                subject="Letter",
                predicate="author",
                value="OLD_SECRET",
                valid_from_scene=1,
                valid_to_scene=5,
                reader_visible_from=2,
                source_ref="author:original",
            ),
        )
        self.store.set_character_knowledge(
            self.project.id,
            self.fact.id,
            CharacterKnowledgeCreate(character="Mira", known_from_scene=2),
        )
        self.url = f"/api/projects/{self.project.id}/story-facts/{self.fact.id}"
        app = FastAPI()
        install_application_error_handlers(app)
        app.include_router(router, prefix="/api")
        app.dependency_overrides[get_data_store] = lambda: self.store
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def change(self, **updates):
        fields = self.fact.model_dump(exclude={"id", "project_id", "version", "updated_at"})
        fields.update(expected_version=self.fact.version, reason="Author correction", **updates)
        return fields

    def knowledge(self, scope="character_knowledge"):
        return next(
            state
            for state in self.store.list_knowledge_states(self.project.id, self.fact.id)
            if state.scope == scope
        )

    def test_fact_correction_preserves_id_sources_and_invalidates_old_character_knowledge(self):
        response = self.client.put(
            self.url,
            json=self.change(
                value="NEW_SECRET",
                valid_from_scene=3,
                reader_visible_from=4,
                source_ref="author:corrected",
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["id"], self.fact.id)
        self.assertEqual(response.json()["version"], 2)
        self.assertEqual(self.store.list_story_facts(self.project.id)[0].version, 2)
        self.assertEqual(self.knowledge().status, "planned")
        self.assertEqual(self.store.list_character_facts_at(self.project.id, "Mira", 4), [])
        self.assertEqual(self.store.list_reader_facts_at(self.project.id, 3), [])
        self.assertEqual(self.store.list_reader_facts_at(self.project.id, 4)[0].value, "NEW_SECRET")
        history = self.client.get(self.url + "/history")
        self.assertEqual(history.status_code, 200)
        facts = [item["record"] for item in history.json() if not item["knowledge_state_id"]]
        self.assertEqual(
            [item["source_ref"] for item in facts], ["author:original", "author:corrected"]
        )
        self.assertEqual([item["value"] for item in facts], ["OLD_SECRET", "NEW_SECRET"])
        with self.store.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM story_fact_character_knowledge"
                ).fetchone()[0],
                0,
            )

    def test_changed_or_retracted_facts_cannot_leak_through_generation_snapshot(self):
        scene = self.store.create_scene_contract(
            self.project.id, SceneContractCreate(sequence=4, title="Reveal", pov="Mira")
        )
        corrected = self.store.correct_story_fact(
            self.project.id,
            self.fact.id,
            StoryFactCorrection(
                **self.change(value="NEW_SECRET", valid_from_scene=3, reader_visible_from=4)
            ),
        )
        snapshot = NarrativeSnapshot.for_scene(
            project_id=self.project.id, scene_id=scene.id, data_store=self.store, cognition=None
        )
        self.assertEqual(snapshot.pov_knowledge, [])
        self.assertNotIn("NEW_SECRET", snapshot.render_generation_context())
        state = self.knowledge()
        self.store.correct_knowledge_state(
            self.project.id,
            self.fact.id,
            state.id,
            KnowledgeStateCorrection(
                scope=state.scope,
                character=state.character,
                known_from_scene=4,
                status="confirmed",
                expected_version=state.version,
                reason="Reviewed new content",
            ),
        )
        snapshot = NarrativeSnapshot.for_scene(
            project_id=self.project.id, scene_id=scene.id, data_store=self.store, cognition=None
        )
        self.assertIn("NEW_SECRET", snapshot.render_generation_context())
        self.store.retract_story_fact(
            self.project.id,
            self.fact.id,
            NarrativeVersionChange(expected_version=corrected.version, reason="Incorrect evidence"),
        )
        snapshot = NarrativeSnapshot.for_scene(
            project_id=self.project.id, scene_id=scene.id, data_store=self.store, cognition=None
        )
        self.assertEqual(snapshot.world_truth, [])
        self.assertEqual(snapshot.reader_knowledge, [])
        self.assertEqual(snapshot.pov_knowledge, [])
        self.assertNotIn("NEW_SECRET", snapshot.render_generation_context())
        self.assertTrue(
            all(
                item.status == "retracted"
                for item in self.store.list_knowledge_states(self.project.id, self.fact.id)
            )
        )

    def test_reader_retraction_updates_compatibility_field_and_invalidates_fact_version(self):
        reader = self.knowledge("reader_knowledge")
        response = self.client.post(
            self.url + f"/knowledge-states/{reader.id}/retract",
            json={"expected_version": reader.version, "reason": "Do not reveal"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(
            self.store.get_story_fact(self.project.id, self.fact.id).reader_visible_from
        )
        self.assertEqual(self.store.list_reader_facts_at(self.project.id, 5), [])
        stale = self.client.put(self.url, json=self.change(value="Should not save"))
        self.assertEqual(stale.status_code, 409)

    def test_query_and_assignment_boundaries_are_inclusive_and_reject_invalid_windows(self):
        for position in (0, 6):
            response = self.client.put(
                self.url + "/character-knowledge",
                json={"character": "Other", "known_from_scene": position},
            )
            self.assertEqual(response.status_code, 422)
        for position in (1, 5):
            response = self.client.put(
                self.url + "/character-knowledge",
                json={"character": "Other", "known_from_scene": position},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                len(self.store.list_character_facts_at(self.project.id, "Other", position)), 1
            )
        for fields in ({"valid_to_scene": 0}, {"reader_visible_from": 6}, {"valid_from_scene": 3}):
            response = self.client.put(self.url, json=self.change(**fields))
            self.assertEqual(response.status_code, 422, response.text)
        for position in (-1, 1000):
            response = self.client.get(
                f"/api/projects/{self.project.id}/story-state?scene_position={position}"
            )
            self.assertEqual(response.status_code, 422)

    def test_cross_project_and_cross_fact_ids_are_not_associated(self):
        other_fact = self.store.create_story_fact(
            self.other.id,
            StoryFactCreate(subject="Private", predicate="is", value="secret", valid_from_scene=1),
        )
        self.store.set_character_knowledge(
            self.other.id,
            other_fact.id,
            CharacterKnowledgeCreate(character="Mira", known_from_scene=1),
        )
        other_state = self.store.list_knowledge_states(self.other.id, other_fact.id)[0]
        foreign_url = f"/api/projects/{self.project.id}/story-facts/{other_fact.id}"
        self.assertEqual(self.client.get(foreign_url + "/history").status_code, 404)
        self.assertEqual(self.client.get(foreign_url + "/knowledge-states").status_code, 404)
        self.assertEqual(self.client.put(foreign_url, json=self.change()).status_code, 404)
        response = self.client.post(
            self.url + f"/knowledge-states/{other_state.id}/retract",
            json={"expected_version": 1, "reason": "Wrong project"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.store.get_story_fact(self.other.id, other_fact.id).version, 1)

    def test_author_knowledge_requires_unique_identity_and_confirmed_fact(self):
        body = {
            "scope": "character_knowledge",
            "character": "Chen",
            "known_from_scene": 3,
            "reason": "Witnessed",
        }
        created = self.client.post(self.url + "/knowledge-states", json=body)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(
            self.client.post(self.url + "/knowledge-states", json=body).status_code, 409
        )
        self.assertEqual(
            self.client.post(
                self.url + "/knowledge-states",
                json={**body, "scope": "world_truth", "character": ""},
            ).status_code,
            422,
        )
        current = created.json()
        changed_identity = {
            **body,
            "character": "Different",
            "expected_version": current["version"],
        }
        self.assertEqual(
            self.client.put(
                self.url + f"/knowledge-states/{current['id']}", json=changed_identity
            ).status_code,
            422,
        )
        self.store.retract_story_fact(
            self.project.id,
            self.fact.id,
            NarrativeVersionChange(expected_version=1, reason="Withdrawn"),
        )
        response = self.client.post(
            self.url + "/knowledge-states", json={**body, "character": "Uninformed"}
        )
        self.assertEqual(response.status_code, 422)

    def test_two_writers_with_same_version_cannot_both_commit(self):
        def correct(value):
            try:
                return self.store.correct_story_fact(
                    self.project.id, self.fact.id, StoryFactCorrection(**self.change(value=value))
                ).version
            except StateConflictError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(correct, ["first", "second"]))
        self.assertCountEqual(outcomes, [2, "conflict"])
        versions = [
            item.version
            for item in self.store.list_narrative_history(self.project.id, self.fact.id)
            if not item.knowledge_state_id
        ]
        self.assertEqual(versions, [1, 2])

    def test_history_failure_rolls_back_fact_and_knowledge_changes(self):
        from app.data.repositories.narrative_maintenance import record_revision

        def fail_after_changes(connection, record, reason):
            if isinstance(record, StoryFact) and record.version == 2:
                raise RuntimeError("History write failed")
            return record_revision(connection, record, reason)

        before = self.store.list_narrative_history(self.project.id, self.fact.id)
        with patch(
            "app.data.repositories.narrative_maintenance.record_revision",
            side_effect=fail_after_changes,
        ):
            with self.assertRaises(RuntimeError):
                self.store.correct_story_fact(
                    self.project.id,
                    self.fact.id,
                    StoryFactCorrection(**self.change(value="discard")),
                )
        self.assertEqual(self.store.get_story_fact(self.project.id, self.fact.id), self.fact)
        self.assertEqual(self.knowledge().status, "confirmed")
        self.assertEqual(self.store.list_narrative_history(self.project.id, self.fact.id), before)

    def test_new_backup_round_trips_corrections_knowledge_and_history(self):
        self.store.correct_story_fact(
            self.project.id, self.fact.id, StoryFactCorrection(**self.change(value="corrected"))
        )
        service = ProjectBackupService(self.store, self.root / "projects")
        package = service.export_package(self.project.id)
        target = SQLiteWritingDataStore(self.root / "restored.db")
        target.init()
        restore = ProjectBackupService(target, self.root / "restored-projects")
        restore.import_package(package)
        self.assertEqual(
            target.list_story_facts(self.project.id), self.store.list_story_facts(self.project.id)
        )
        self.assertEqual(
            target.list_knowledge_states(self.project.id, self.fact.id),
            self.store.list_knowledge_states(self.project.id, self.fact.id),
        )
        self.assertEqual(
            target.list_narrative_history(self.project.id, self.fact.id),
            self.store.list_narrative_history(self.project.id, self.fact.id),
        )

    def test_old_backup_without_versions_or_history_restores_and_captures_baseline(self):
        service = ProjectBackupService(self.store, self.root / "projects")
        with ZipFile(io.BytesIO(service.export_package(self.project.id))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            data = json.loads(archive.read("data.json"))
        tables = data["tables"]
        tables.pop("narrative_revisions")
        for table in ("manuscript_volumes", "manuscript_volume_chapters"):
            tables.pop(table)
            manifest["tables"].remove(table)
            manifest["project"]["row_counts"].pop(table)
        for row in tables["outbox_jobs"]:
            row.pop("execution_json", None)
        for row in tables["reference_suggestions"]:
            row.pop("editor_context_json", None)
        for table in ("story_facts", "knowledge_states"):
            for row in tables[table]:
                row.pop("version")
                row.pop("updated_at")
        manifest["schema_version"] = 15
        manifest["tables"].remove("narrative_revisions")
        manifest["project"]["row_counts"].pop("narrative_revisions")
        output = io.BytesIO()
        with ZipFile(output, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("data.json", json.dumps(data))
        service.import_package(output.getvalue(), overwrite=True)
        corrected = self.store.correct_story_fact(
            self.project.id, self.fact.id, StoryFactCorrection(**self.change(value="corrected"))
        )
        self.assertEqual(corrected.version, 2)
        history = self.store.list_narrative_history(self.project.id, self.fact.id)
        self.assertEqual(
            [item.record.value for item in history if not item.knowledge_state_id],
            ["OLD_SECRET", "corrected"],
        )

    def test_backup_rejects_mismatched_history_payload_without_touching_current_data(self):
        service = ProjectBackupService(self.store, self.root / "projects")
        with ZipFile(io.BytesIO(service.export_package(self.project.id))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            data = json.loads(archive.read("data.json"))
        row = data["tables"]["narrative_revisions"][0]
        payload = json.loads(row["record_json"])
        payload["project_id"] = self.other.id
        row["record_json"] = json.dumps(payload)
        output = io.BytesIO()
        with ZipFile(output, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("data.json", json.dumps(data))
        with self.assertRaises(BackupError):
            service.import_package(output.getvalue(), overwrite=True)
        self.assertEqual(self.store.get_story_fact(self.project.id, self.fact.id), self.fact)

    def test_migration_15_preserves_old_fact_and_adds_version_once(self):
        connection = sqlite3.connect(self.root / "legacy.db")
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        with patch("app.data.migrations.MIGRATIONS", MIGRATIONS[:15]):
            run_migrations(connection)
        connection.execute(
            "INSERT INTO projects(id,title,premise,current_step) VALUES('legacy','Legacy','Old',1)"
        )
        connection.execute(
            "INSERT INTO story_facts(id,project_id,subject,predicate,value,valid_from_scene) VALUES('fact','legacy','Letter','author','Original',1)"
        )
        connection.commit()
        self.assertEqual(run_migrations(connection), sum(m.version > 15 for m in MIGRATIONS))
        self.assertEqual(run_migrations(connection), 0)
        row = connection.execute(
            "SELECT value, version FROM story_facts WHERE id='fact'"
        ).fetchone()
        self.assertEqual(tuple(row), ("Original", 1))


if __name__ == "__main__":
    unittest.main()
