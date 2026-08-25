from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import (
    CanonEntityCreate,
    ProjectCreate,
    WritebackProposalCreate,
)
from app.review.writeback_apply import (
    WritebackTargetMissingError,
    WritebackVersionConflictError,
)


def _create_project(client: TestClient, title: str) -> str:
    response = client.post(
        "/api/projects",
        json={"title": title, "premise": "Write-back update flow test."},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _update_proposal(
    entity_id: str,
    expected_version: int,
    *,
    changes: dict | None = None,
) -> WritebackProposalCreate:
    return WritebackProposalCreate(
        target="canon_entity",
        action="update",
        title="Update Lin Ye injury state",
        rationale="The accepted revision establishes a right-arm injury.",
        source_ref="manuscript_revision:revision-24",
        target_record_id=entity_id,
        expected_version=expected_version,
        changes=changes
        or {
            "current_state": {
                "before": "Uninjured",
                "after": "Right arm injured",
            }
        },
    )


class WritebackUpdateStoreTests(unittest.TestCase):
    def test_accepted_update_proposal_applies_changes_and_bumps_version(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Update", premise="P."))
            entity = store.create_canon_entity(
                project.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Lin Ye",
                    current_state="Uninjured",
                ),
            )
            proposal = store.create_writeback_proposal(
                project.id,
                _update_proposal(entity.id, 1),
            )

            accepted = store.update_writeback_proposal_status(project.id, proposal.id, "accepted")

            self.assertEqual(accepted.status, "accepted")
            self.assertEqual(accepted.applied_record_id, entity.id)
            updated = store.get_canon_entity(project.id, entity.id)
            self.assertEqual(updated.current_state, "Right arm injured")
            self.assertEqual(updated.version, 2)
            self.assertTrue(updated.updated_at)

    def test_accepting_a_stale_update_proposal_conflicts_without_applying(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Stale", premise="P."))
            entity = store.create_canon_entity(
                project.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Lin Ye",
                    current_state="Uninjured",
                ),
            )
            proposal = store.create_writeback_proposal(
                project.id,
                _update_proposal(entity.id, 1),
            )
            # Concurrent manual edit moves the record to version 2.
            store.update_canon_entity(
                project.id,
                entity.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Lin Ye",
                    current_state="Edited elsewhere",
                ),
            )

            with self.assertRaises(WritebackVersionConflictError):
                store.update_writeback_proposal_status(project.id, proposal.id, "accepted")

            still_pending = store.get_writeback_proposal(project.id, proposal.id)
            untouched = store.get_canon_entity(project.id, entity.id)
        self.assertEqual(still_pending.status, "pending_review")
        self.assertEqual(untouched.version, 2)
        self.assertEqual(untouched.current_state, "Edited elsewhere")

    def test_accepting_an_update_for_a_missing_record_raises_target_missing(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Ghost", premise="P."))
            proposal = store.create_writeback_proposal(
                project.id,
                _update_proposal("canon-character-ghost", 1),
            )

            with self.assertRaises(WritebackTargetMissingError):
                store.update_writeback_proposal_status(project.id, proposal.id, "accepted")

    def test_accepting_one_update_supersedes_sibling_updates_for_the_record(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Siblings", premise="P."))
            entity = store.create_canon_entity(
                project.id,
                CanonEntityCreate(
                    entity_type="character",
                    name="Lin Ye",
                    current_state="Uninjured",
                ),
            )
            first = store.create_writeback_proposal(project.id, _update_proposal(entity.id, 1))
            second = store.create_writeback_proposal(project.id, _update_proposal(entity.id, 1))

            store.update_writeback_proposal_status(project.id, first.id, "accepted")

            statuses = {
                proposal.id: proposal.status
                for proposal in store.list_writeback_proposals(project.id)
            }
        self.assertEqual(statuses[first.id], "accepted")
        self.assertEqual(statuses[second.id], "superseded")


class WritebackCreationValidationRouteTests(unittest.TestCase):
    """P1-03: invalid proposals are rejected before they reach the database."""

    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        store = SQLiteWritingDataStore(Path(self._temp.name) / "app.db")
        store.init()
        self.store = store
        app.dependency_overrides[get_data_store] = lambda: store
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.project_id = _create_project(self.client, "Prevalidation")

    def _post(self, payload: dict):
        return self.client.post(
            f"/api/projects/{self.project_id}/writeback/proposals",
            json=payload,
        )

    def test_valid_create_proposal_is_still_accepted_by_the_gate(self) -> None:
        response = self._post(
            {
                "target": "memory_record",
                "action": "create",
                "title": "Voice",
                "payload": {
                    "record_type": "voice_sample",
                    "title": "Voice",
                    "content": "Quiet.",
                },
            }
        )
        self.assertEqual(response.status_code, 201)

    def test_update_with_unknown_target_is_rejected_with_422(self) -> None:
        response = self._post(
            {
                "target": "canon_entity",
                "action": "update",
                "title": "Ghost update",
                "target_record_id": "canon-character-ghost",
                "expected_version": 1,
                "changes": {"current_state": {"before": "A", "after": "B"}},
            }
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.store.list_writeback_proposals(self.project_id), [])

    def test_update_with_stale_expected_version_is_rejected_with_422(self) -> None:
        created = self.client.post(
            f"/api/projects/{self.project_id}/canon/entities",
            json={"entity_type": "character", "name": "Lin Ye"},
        ).json()
        # Manual edit bumps the record to version 2.
        self.client.put(
            f"/api/projects/{self.project_id}/canon/entities/{created['id']}",
            json={"entity_type": "character", "name": "Lin Ye", "current_state": "Worn"},
        )

        stale = self._post(
            {
                "target": "canon_entity",
                "action": "update",
                "title": "Stale update",
                "target_record_id": created["id"],
                "expected_version": 1,
                "changes": {"current_state": {"before": "", "after": "Hurt"}},
            }
        )
        fresh = self._post(
            {
                "target": "canon_entity",
                "action": "update",
                "title": "Fresh update",
                "target_record_id": created["id"],
                "expected_version": 2,
                "changes": {"current_state": {"before": "Worn", "after": "Hurt"}},
            }
        )

        self.assertEqual(stale.status_code, 422)
        self.assertEqual(fresh.status_code, 201)

    def test_update_with_unknown_field_or_bad_shape_is_rejected(self) -> None:
        created = self.client.post(
            f"/api/projects/{self.project_id}/canon/entities",
            json={"entity_type": "character", "name": "Mira"},
        ).json()

        unknown_field = self._post(
            {
                "target": "canon_entity",
                "action": "update",
                "title": "Bad field",
                "target_record_id": created["id"],
                "expected_version": 1,
                "changes": {"secret_note": {"before": "", "after": "x"}},
            }
        )
        missing_after = self._post(
            {
                "target": "canon_entity",
                "action": "update",
                "title": "Missing after",
                "target_record_id": created["id"],
                "expected_version": 1,
                "changes": {"current_state": {"before": ""}},
            }
        )
        no_changes = self._post(
            {
                "target": "canon_entity",
                "action": "update",
                "title": "No changes",
                "target_record_id": created["id"],
                "expected_version": 1,
                "changes": {},
            }
        )

        for response in (unknown_field, missing_after, no_changes):
            self.assertEqual(response.status_code, 422)

    def test_memory_update_and_blank_name_updates_are_rejected(self) -> None:
        unsupported = self._post(
            {
                "target": "memory_record",
                "action": "update",
                "title": "Memory update",
                "target_record_id": "whatever",
                "expected_version": 1,
                "changes": {"content": {"before": "", "after": "New"}},
            }
        )
        blank_name = self._post(
            {
                "target": "canon_entity",
                "action": "update",
                "title": "Blank name",
                "target_record_id": "canon-character-x",
                "expected_version": 3,
                "changes": {"name": {"before": "X", "after": "   "}},
            }
        )

        self.assertEqual(unsupported.status_code, 422)
        self.assertEqual(blank_name.status_code, 422)

    def test_create_proposal_duplicate_canon_name_is_rejected_before_insert(
        self,
    ) -> None:
        self.client.post(
            f"/api/projects/{self.project_id}/canon/entities",
            json={"entity_type": "character", "name": "Mira"},
        )
        duplicate = self._post(
            {
                "target": "canon_entity",
                "action": "create",
                "title": "Duplicate Mira",
                "payload": {
                    "entity_type": "character",
                    "name": "mira",
                    "summary": "Case-insensitive duplicate.",
                },
            }
        )

        self.assertEqual(duplicate.status_code, 422)
        self.assertEqual(len(self.store.list_writeback_proposals(self.project_id)), 0)


if __name__ == "__main__":
    unittest.main()
