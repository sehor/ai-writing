"""P1-05 regression tests: structured Snowflake compiler.

Covers the Step 7 canon extractor, the Step 8 scene parser, their
idempotent compile routes, and the transactional batch acceptance of
parsed scene proposals.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import CanonEntity, ManuscriptChapter
from app.snowflake_compiler import (
    ArtifactNotParseableError,
    extract_canon_proposals,
    parse_scene_artifact,
)


SCENE_ARTIFACT = """# Scene List

### Scene 1: Opening
- POV: Mira Vale
- Goal: Reach the archive before dusk.
- Conflict: The archivist refuses entry.
- Turning point: Mira burns her map to prove intent.
- Outcome: Mira enters, but the burned map strands her inside.
- Information Delta: Mira learns the archive admits a sacrifice.
- Character State Delta: Mira loses her only trusted route.
- Required Canon: Mira Vale; Glass City
- Forbidden facts: The city rewrites its maps at night
- Open threads: Who guards the lower vault?
- Chapter hint: Chapter 1

### Scene 2: The Bargain
- POV: Juno Ash
- Goal: Trade a forged seal for passage.
- Conflict: Juno is recognized.
- Turning point: The guard demands a name.
- Outcome: Juno gives Mira's name and creates a new enemy.
- Information Delta: The guard connects Juno to Mira.
- Character State Delta: Juno commits to the deception.
"""

CANON_ARTIFACT = """# Character Bible

## Character: Mira Vale
- Type: character
- Confirmed: yes
- Summary: A disgraced cartographer.
- Current state: Hiding in the glass district.
- Constraints: Cannot read rewritten maps.
- Last seen: Act I
- Timeline notes: Exiled after the survey incident.

## Location: Glass City
- Type: location
- Confirmed: yes
- Summary: A city that rewrites itself nightly.
"""

CANON_RECORDS = [
    {
        "record_id": "character-mira-vale",
        "position": 1,
        "payload": {
            "record_type": "character",
            "name": "Mira Vale",
            "role": "protagonist",
            "one_sentence_summary": "A disgraced cartographer.",
            "motivation": "Restore her place in the city.",
            "goal": "Reach the archive.",
            "conflict": "She cannot read rewritten maps.",
            "epiphany": "A changing map can still be home.",
            "viewpoint_summary": "Mira distrusts every route after exile.",
            "confirmed_facts": [
                "A disgraced cartographer.",
                "Cannot read rewritten maps.",
            ],
        },
    },
    {
        "record_id": "location-glass-city",
        "position": 2,
        "payload": {
            "record_type": "location",
            "name": "Glass City",
            "summary": "A city that rewrites itself nightly.",
            "confirmed_facts": ["The city rewrites itself nightly."],
        },
    },
]

SCENE_RECORDS = [
    {
        "record_id": "scene-opening",
        "position": 1,
        "payload": {
            "title": "Opening",
            "pov": "Mira Vale",
            "goal": "Reach the archive before dusk.",
            "conflict": "The archivist refuses entry.",
            "turning_point": "Mira burns her map to prove intent.",
            "outcome": "Mira enters, but the burned map strands her inside.",
            "required_canon_ids": [],
            "forbidden_facts": ["The city rewrites its maps at night"],
            "information_delta": "Mira learns the archive admits a sacrifice.",
            "character_state_delta": "Mira loses her only trusted route.",
            "story_thread_actions": [],
        },
    },
    {
        "record_id": "scene-bargain",
        "position": 2,
        "payload": {
            "title": "The Bargain",
            "pov": "Juno Ash",
            "goal": "Trade a forged seal for passage.",
            "conflict": "Juno is recognized.",
            "turning_point": "The guard demands a name.",
            "outcome": "Juno gives Mira's name and creates a new enemy.",
            "required_canon_ids": [],
            "forbidden_facts": [],
            "information_delta": "The guard connects Juno to Mira.",
            "character_state_delta": "Juno commits to the deception.",
            "story_thread_actions": [],
        },
    },
]


def make_canon_entity(entity_id: str, name: str, entity_type: str = "character") -> CanonEntity:
    return CanonEntity(
        id=entity_id,
        project_id="p1",
        entity_type=entity_type,  # type: ignore[arg-type]
        name=name,
        summary="",
        current_state="",
        constraints="",
        last_seen="",
        timeline_notes="",
        version=1,
        updated_at="",
    )


def make_chapter(chapter_id: str, sequence: int, title: str) -> ManuscriptChapter:
    return ManuscriptChapter(id=chapter_id, project_id="p1", sequence=sequence, title=title)


class SceneParserUnitTests(unittest.TestCase):
    def test_parses_local_scene_format(self) -> None:
        canon = [
            make_canon_entity("canon-mira", "Mira Vale"),
            make_canon_entity("canon-city", "Glass City", "location"),
        ]
        chapters = [make_chapter("ch-1", 1, "Chapter 1")]
        outcome = parse_scene_artifact(SCENE_ARTIFACT, canon_entities=canon, chapters=chapters)

        self.assertEqual(len(outcome.scenes), 2)
        first = outcome.scenes[0]
        self.assertEqual(first.sequence, 1)
        self.assertEqual(first.title, "Opening")
        self.assertEqual(first.pov, "Mira Vale")
        self.assertIn("archive before dusk", first.goal)
        self.assertIn("burns her map", first.turning_point)
        self.assertEqual(first.resolved_canon_ids, ["canon-mira", "canon-city"])
        self.assertIn("rewrites its maps", first.forbidden_fact_refs)
        self.assertIn("lower vault", first.open_threads)
        self.assertEqual(first.resolved_chapter_id, "ch-1")

    def test_missing_core_fields_produce_warnings(self) -> None:
        outcome = parse_scene_artifact("Scene 3\n- Goal: Survive the night.")
        scene = outcome.scenes[0]
        joined = "\n".join(scene.blocking_errors)
        self.assertIn("missing", joined)
        for field in (
            "pov",
            "conflict",
            "turning_point",
            "outcome",
            "information_delta",
            "character_state_delta",
        ):
            self.assertIn(field, joined)
        self.assertEqual(scene.title, "Scene 3")
        self.assertTrue(any("no title" in warning for warning in scene.warnings))

    def test_tbd_fields_are_flagged_and_left_empty(self) -> None:
        outcome = parse_scene_artifact("### Scene 5\n- POV: TBD\n- Goal: TBD")
        scene = outcome.scenes[0]
        self.assertEqual(scene.pov, "")
        self.assertEqual(scene.goal, "")
        self.assertTrue(any("TBD" in warning for warning in scene.warnings))

    def test_duplicate_sequences_are_renumbered_with_warning(self) -> None:
        content = "Scene 1\n- Goal: a\n\nScene 1\n- Goal: b"
        outcome = parse_scene_artifact(content)
        self.assertEqual([scene.sequence for scene in outcome.scenes], [1, 2])
        self.assertTrue(any("re-sequenced" in warning for warning in outcome.scenes[1].warnings))

    def test_unknown_canon_reference_is_reported(self) -> None:
        outcome = parse_scene_artifact(
            "Scene 1\n- Required Canon: Ghost Harbour",
            canon_entities=[make_canon_entity("c1", "Mira Vale")],
        )
        self.assertEqual(outcome.scenes[0].resolved_canon_ids, [])
        self.assertTrue(
            any("Ghost Harbour" in finding for finding in outcome.scenes[0].blocking_errors)
        )

    def test_chapter_hint_resolves_by_number_and_title(self) -> None:
        chapters = [make_chapter("ch-9", 9, "The Long Fall")]
        outcome = parse_scene_artifact(
            "Scene 1\n- Chapter hint: 9\n\nScene 2\n- Chapter hint: the long fall",
            chapters=chapters,
        )
        self.assertEqual(outcome.scenes[0].resolved_chapter_id, "ch-9")
        self.assertEqual(outcome.scenes[1].resolved_chapter_id, "ch-9")

    def test_unparseable_content_raises_before_anything_persists(self) -> None:
        with self.assertRaises(ArtifactNotParseableError):
            parse_scene_artifact("Just some prose without any scene headers.")


class CanonExtractorUnitTests(unittest.TestCase):
    def test_character_profile_is_not_canon_without_explicit_confirmation(self) -> None:
        extraction = extract_canon_proposals(
            """## Character: Mira Vale
- Type: character
- Motivation: Find a home.
- Summary: A displaced cartographer.
""",
            [],
            source_ref="snowflake_artifact:p1:7",
        )
        self.assertEqual(extraction.proposals, [])
        self.assertTrue(any("Confirmed: yes" in warning for warning in extraction.warnings))
        self.assertTrue(any("Motivation" in warning for warning in extraction.warnings))

    def test_creates_proposals_for_new_entities(self) -> None:
        extraction = extract_canon_proposals(
            CANON_ARTIFACT, [], source_ref="snowflake_artifact:p1:7"
        )
        self.assertEqual(len(extraction.proposals), 2)
        create = extraction.proposals[0]
        self.assertEqual(create.target, "canon_entity")
        self.assertEqual(create.action, "create")
        self.assertEqual(create.payload["name"], "Mira Vale")
        self.assertEqual(create.payload["entity_type"], "character")
        self.assertEqual(create.source_ref, "snowflake_artifact:p1:7")
        self.assertIn("Snowflake Step 7", create.rationale)
        types = {
            proposal.payload["name"]: proposal.payload["entity_type"]
            for proposal in extraction.proposals
        }
        self.assertEqual(types["Glass City"], "location")

    def test_builds_update_proposal_for_changed_existing_entity(self) -> None:
        existing = CanonEntity(
            id="canon-mira",
            project_id="p1",
            entity_type="character",
            name="Mira Vale",
            summary="A cartographer.",
            current_state="Uninjured.",
            constraints="",
            last_seen="",
            timeline_notes="",
            version=3,
            updated_at="",
        )
        extraction = extract_canon_proposals(
            CANON_ARTIFACT, [existing], source_ref="snowflake_artifact:p1:7"
        )
        updates = [proposal for proposal in extraction.proposals if proposal.action == "update"]
        creates = [proposal for proposal in extraction.proposals if proposal.action == "create"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(len(creates), 1)  # Glass City stays a create
        update = updates[0]
        self.assertEqual(update.target_record_id, "canon-mira")
        self.assertEqual(update.expected_version, 3)
        change = update.changes["current_state"]
        self.assertEqual(change["before"], "Uninjured.")
        self.assertEqual(change["after"], "Hiding in the glass district.")

    def test_identical_entity_produces_warning_not_proposal(self) -> None:
        from app.models import CanonEntityCreate

        identical = CanonEntityCreate(
            entity_type="character",
            name="Mira Vale",
            summary="A disgraced cartographer.",
            current_state="Hiding in the glass district.",
            constraints="Cannot read rewritten maps.",
            last_seen="Act I",
            timeline_notes="Exiled after the survey incident.",
        )
        existing = CanonEntity(
            id="canon-mira",
            project_id="p1",
            version=1,
            updated_at="",
            **identical.model_dump(),
        )
        extraction = extract_canon_proposals(
            CANON_ARTIFACT.replace(
                "- Summary: A disgraced cartographer.", "- Summary: A disgraced cartographer."
            ),
            [existing],
            source_ref="snowflake_artifact:p1:7",
        )
        names = [proposal.title for proposal in extraction.proposals]
        self.assertFalse(any("Mira Vale" in title and "Update" in title for title in names))
        self.assertTrue(any("already matches" in warning for warning in extraction.warnings))

    def test_unparseable_bible_raises(self) -> None:
        with self.assertRaises(ArtifactNotParseableError):
            extract_canon_proposals("Freeform brainstorm with no blocks.", [], source_ref="x")

    def test_overlong_values_are_truncated_to_model_limits(self) -> None:
        huge = CANON_ARTIFACT.replace(
            "A disgraced cartographer.", "A disgraced cartographer. " + "x" * 5000
        )
        extraction = extract_canon_proposals(huge, [], source_ref="x")
        payload = extraction.proposals[0].payload
        self.assertLessEqual(len(payload["summary"]), 1000)


class CompilerRouteTests(unittest.TestCase):
    def _client(self):
        temp_dir = TemporaryDirectory()
        store = SQLiteWritingDataStore(Path(temp_dir.name) / "app.db")
        store.init()
        app.dependency_overrides[get_data_store] = lambda: store
        client_context = TestClient(app)
        client = client_context.__enter__()
        client._dsh_client_context = client_context
        client._dsh_temp_dir = temp_dir  # keep alive until cleanup
        return client, store

    def _cleanup(self, client) -> None:
        client._dsh_client_context.__exit__(None, None, None)
        app.dependency_overrides.clear()
        client._dsh_temp_dir.cleanup()

    def _create_project(self, client: TestClient) -> str:
        unique = abs(hash(self.id())) % 100000
        created = client.post(
            "/api/projects",
            json={"title": f"Compiler Project {unique}", "premise": "Compile artifacts."},
        )
        self.assertEqual(created.status_code, 201, created.text)
        return created.json()["id"]

    def _save_records(
        self,
        client: TestClient,
        project_id: str,
        step: int,
        records: list[dict],
    ) -> None:
        current = client.get(
            f"/api/projects/{project_id}/snowflake/steps/{step}/records?page_size=100"
        ).json()["data"]
        accepted_by_id = {
            item["record_id"]: item["id"] for item in current if item["status"] == "accepted"
        }
        for record in records:
            expected = accepted_by_id.get(record["record_id"], "")
            response = client.post(
                f"/api/projects/{project_id}/snowflake/record-revisions",
                json={
                    "step_number": step,
                    "record_id": record["record_id"],
                    "position": record["position"],
                    "payload": record["payload"],
                    "base_revision_id": expected,
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            accepted = client.post(
                f"/api/projects/{project_id}/snowflake/record-revisions/"
                f"{response.json()['id']}/decisions",
                json={"decision": "accepted", "expected_revision_id": expected},
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_step7_extraction_is_idempotent_and_reviewable(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            self._save_records(client, project_id, 7, CANON_RECORDS)

            first = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/compile-canon-proposals"
            )
            self.assertEqual(first.status_code, 201, first.text)
            report = first.json()
            self.assertFalse(report["cached"])
            self.assertEqual(len(report["proposals"]), 2)
            self.assertTrue(all(p["status"] == "pending_review" for p in report["proposals"]))
            self.assertTrue(all(p["source_ref"].endswith(":7") for p in report["proposals"]))

            repeat = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/compile-canon-proposals"
            ).json()
            self.assertTrue(repeat["cached"])
            self.assertEqual(
                sorted(p["id"] for p in repeat["proposals"]),
                sorted(p["id"] for p in report["proposals"]),
            )

            stored = client.get(f"/api/projects/{project_id}/writeback/proposals").json()
            self.assertEqual(len(stored), 2)  # no duplicates from the replay

            target_id = report["proposals"][0]["id"]
            accepted = client.put(
                f"/api/projects/{project_id}/writeback/proposals/{target_id}/status",
                json={"status": "accepted"},
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            canon_names = [
                entity["name"]
                for entity in client.get(f"/api/projects/{project_id}/canon/entities").json()
            ]
            self.assertIn(report["proposals"][0]["payload"]["name"], canon_names)
        finally:
            self._cleanup(client)

    def test_forced_reextraction_supersedes_stale_pending_proposals(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            self._save_records(client, project_id, 7, CANON_RECORDS)
            initial = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/compile-canon-proposals"
            ).json()

            edited = CANON_RECORDS + [
                {
                    "record_id": "item-forged-seal",
                    "position": 3,
                    "payload": {
                        "record_type": "item",
                        "name": "Forged Seal",
                        "summary": "A forged archive seal.",
                        "confirmed_facts": ["The seal is a forged archive credential."],
                    },
                }
            ]
            self._save_records(client, project_id, 7, edited)
            rerun = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/compile-canon-proposals?force=true"
            )
            self.assertEqual(rerun.status_code, 201, rerun.text)
            fresh = rerun.json()
            self.assertFalse(fresh["cached"])
            fresh_titles = [proposal["title"] for proposal in fresh["proposals"]]
            self.assertTrue(any("Forged Seal" in title for title in fresh_titles))

            statuses = {
                proposal["id"]: proposal["status"]
                for proposal in client.get(f"/api/projects/{project_id}/writeback/proposals").json()
            }
            for old in initial["proposals"]:
                self.assertEqual(statuses[old["id"]], "superseded")
            for new in fresh["proposals"]:
                self.assertEqual(statuses[new["id"]], "pending_review")
        finally:
            self._cleanup(client)

    def test_repeat_compile_after_acceptance_does_not_duplicate_pending(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            self._save_records(client, project_id, 7, CANON_RECORDS)
            first = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/compile-canon-proposals"
            ).json()

            # Accepting the first proposal changes the Canon context, so
            # the cached run no longer applies; the extractor re-runs and
            # must not stack a second pending proposal for the same entity.
            accepted_id = first["proposals"][0]["id"]
            accept = client.put(
                f"/api/projects/{project_id}/writeback/proposals/{accepted_id}/status",
                json={"status": "accepted"},
            )
            self.assertEqual(accept.status_code, 200, accept.text)

            second = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/compile-canon-proposals"
            )
            self.assertEqual(second.status_code, 201, second.text)
            report = second.json()
            self.assertFalse(report["cached"])

            pending_titles = [
                proposal["title"]
                for proposal in client.get(f"/api/projects/{project_id}/writeback/proposals").json()
                if proposal["status"] == "pending_review"
            ]
            self.assertEqual(len(pending_titles), len(set(pending_titles)))
            self.assertTrue(
                any("already pending review" in warning for warning in report["warnings"])
            )
        finally:
            self._cleanup(client)

    def test_compile_routes_enforce_their_step(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            wrong_canon = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/8/compile-canon-proposals"
            )
            self.assertEqual(wrong_canon.status_code, 422)
            wrong_scenes = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/parse-scene-proposals"
            )
            self.assertEqual(wrong_scenes.status_code, 422)
            missing = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/7/compile-canon-proposals"
            )
            self.assertEqual(missing.status_code, 404)
        finally:
            self._cleanup(client)

    def test_invalid_step8_record_is_rejected_before_it_can_pollute_compiler_state(self) -> None:
        try:
            client, store = self._client()
            project_id = self._create_project(client)
            invalid = client.post(
                f"/api/projects/{project_id}/snowflake/record-revisions",
                json={
                    "step_number": 8,
                    "record_id": "invalid-scene",
                    "position": 1,
                    "payload": {"title": "Loose prose, no scene contract."},
                },
            )
            self.assertEqual(invalid.status_code, 422, invalid.text)
            failed = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/8/parse-scene-proposals"
            )
            self.assertEqual(failed.status_code, 404)
            self.assertEqual(
                client.get(f"/api/projects/{project_id}/snowflake/scene-proposals").json(), []
            )
            with store.connect() as connection:
                rows = connection.execute(
                    "SELECT status FROM analysis_runs WHERE processor='local_scene_parser'"
                ).fetchall()
            self.assertEqual(rows, [])
        finally:
            self._cleanup(client)

    def test_step8_accept_blocks_unknown_canon_before_head_changes(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            payload = dict(SCENE_RECORDS[0]["payload"])
            payload["required_canon_ids"] = ["canon-does-not-exist"]
            created = client.post(
                f"/api/projects/{project_id}/snowflake/record-revisions",
                json={
                    "step_number": 8,
                    "record_id": "scene-invalid-canon",
                    "position": 1,
                    "payload": payload,
                },
            )
            self.assertEqual(created.status_code, 201, created.text)
            decision = client.post(
                f"/api/projects/{project_id}/snowflake/record-revisions/"
                f"{created.json()['id']}/decisions",
                json={"decision": "accepted", "expected_revision_id": ""},
            )
            self.assertEqual(decision.status_code, 422, decision.text)
            codes = {
                finding["code"]
                for finding in decision.json()["detail"]["validation_report"]["findings"]
            }
            self.assertIn("unknown_required_canon", codes)
            current = client.get(f"/api/projects/{project_id}/snowflake/steps/8/records").json()[
                "data"
            ]
            self.assertEqual(current[0]["status"], "draft")
            artifact = client.get(f"/api/projects/{project_id}/snowflake/artifacts/8")
            self.assertEqual(artifact.status_code, 404)
        finally:
            self._cleanup(client)

    def test_scene_compiler_ignores_newer_unaccepted_record_revision(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            self._save_records(client, project_id, 8, [SCENE_RECORDS[0]])
            accepted = client.get(f"/api/projects/{project_id}/snowflake/steps/8/records").json()[
                "data"
            ][0]
            poisoned = dict(SCENE_RECORDS[0]["payload"])
            poisoned["title"] = "UNACCEPTED TITLE MUST NOT COMPILE"
            pending = client.post(
                f"/api/projects/{project_id}/snowflake/record-revisions",
                json={
                    "step_number": 8,
                    "record_id": accepted["record_id"],
                    "position": accepted["position"],
                    "payload": poisoned,
                    "base_revision_id": accepted["id"],
                    "source": "ai",
                },
            )
            self.assertEqual(pending.status_code, 201, pending.text)

            report = client.post(
                f"/api/projects/{project_id}/snowflake/records/8/parse-scene-proposals"
            )
            self.assertEqual(report.status_code, 201, report.text)
            self.assertEqual(report.json()["proposals"][0]["title"], "Opening")
            self.assertNotIn("UNACCEPTED", report.text)
        finally:
            self._cleanup(client)

    def test_step8_parse_is_idempotent_and_batch_accept_creates_contracts(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            client.post(
                f"/api/projects/{project_id}/manuscript/chapters",
                json={"sequence": 1, "title": "Chapter 1"},
            )
            chapters = client.get(f"/api/projects/{project_id}/manuscript/chapters").json()
            self.assertEqual(len(chapters), 1)
            self._save_records(client, project_id, 8, SCENE_RECORDS)

            parsed = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/8/parse-scene-proposals"
            )
            self.assertEqual(parsed.status_code, 201, parsed.text)
            report = parsed.json()
            self.assertFalse(report["cached"])
            self.assertEqual(len(report["proposals"]), 2)
            first_sequence = report["proposals"][0]
            self.assertEqual(first_sequence["chapter_hint"], "")
            self.assertEqual(first_sequence["chapter_id"], "")
            self.assertEqual(
                first_sequence["information_delta"],
                SCENE_RECORDS[0]["payload"]["information_delta"],
            )
            self.assertEqual(
                first_sequence["character_state_delta"],
                SCENE_RECORDS[0]["payload"]["character_state_delta"],
            )

            replay = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/8/parse-scene-proposals"
            ).json()
            self.assertTrue(replay["cached"])
            self.assertEqual(
                sorted(p["id"] for p in replay["proposals"]),
                sorted(p["id"] for p in report["proposals"]),
            )

            listed = client.get(f"/api/projects/{project_id}/snowflake/scene-proposals").json()
            self.assertEqual(len(listed), 2)
            self.assertTrue(all(item["status"] == "pending_review" for item in listed))

            accepted = client.post(
                f"/api/projects/{project_id}/snowflake/scene-proposals/accept",
                json={"proposal_ids": []},
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            acceptance = accepted.json()
            self.assertEqual(len(acceptance["scenes"]), 2)
            self.assertTrue(
                all(proposal["status"] == "accepted" for proposal in acceptance["proposals"])
            )
            self.assertTrue(
                all(proposal["applied_scene_id"] for proposal in acceptance["proposals"])
            )

            contracts = client.get(f"/api/projects/{project_id}/scene-contracts").json()
            self.assertEqual(len(contracts), 2)
            sequences = sorted(contract["sequence"] for contract in contracts)
            self.assertEqual(sequences, [1, 2])

            again = client.post(
                f"/api/projects/{project_id}/snowflake/scene-proposals/accept",
                json={"proposal_ids": []},
            )
            self.assertEqual(again.status_code, 200)
            self.assertEqual(again.json()["scenes"], [])
        finally:
            self._cleanup(client)

    def test_batch_accept_conflict_rolls_back_everything(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            pre_existing = client.post(
                f"/api/projects/{project_id}/scene-contracts",
                json={"sequence": 1, "title": "Already here"},
            )
            self.assertEqual(pre_existing.status_code, 201)
            self._save_records(client, project_id, 8, SCENE_RECORDS)
            client.post(f"/api/projects/{project_id}/snowflake/artifacts/8/parse-scene-proposals")

            conflict = client.post(
                f"/api/projects/{project_id}/snowflake/scene-proposals/accept",
                json={"proposal_ids": []},
            )
            self.assertEqual(conflict.status_code, 409)

            contracts = client.get(f"/api/projects/{project_id}/scene-contracts").json()
            self.assertEqual(len(contracts), 1)  # nothing partial was committed
            proposals = client.get(f"/api/projects/{project_id}/snowflake/scene-proposals").json()
            self.assertTrue(all(item["status"] == "pending_review" for item in proposals))
        finally:
            self._cleanup(client)

    def test_step8_creates_reviewable_story_thread_and_event_proposals(self) -> None:
        records = [
            {
                "record_id": "scene-signal",
                "position": 1,
                "payload": {
                    "title": "The Signal",
                    "pov": "Mira",
                    "goal": "Reach the tower.",
                    "conflict": "The stairs collapse.",
                    "turning_point": "A coded light answers her.",
                    "outcome": "Mira is trapped above the city.",
                    "required_canon_ids": [],
                    "forbidden_facts": [],
                    "information_delta": "The watcher knows her route.",
                    "character_state_delta": "Mira stops trusting the map.",
                    "story_thread_actions": [
                        {"action": "plant", "thread_title": "The coded watcher"}
                    ],
                },
            }
        ]
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            self._save_records(client, project_id, 8, records)
            report = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/8/parse-scene-proposals"
            ).json()
            self.assertEqual(
                [item["target"] for item in report["thread_proposals"]],
                ["story_thread", "story_thread_event"],
            )

            create_thread, create_event = report["thread_proposals"]
            accepted_thread = client.put(
                f"/api/projects/{project_id}/writeback/proposals/{create_thread['id']}/status",
                json={"status": "accepted"},
            )
            self.assertEqual(accepted_thread.status_code, 200, accepted_thread.text)
            premature_event = client.put(
                f"/api/projects/{project_id}/writeback/proposals/{create_event['id']}/status",
                json={"status": "accepted"},
            )
            self.assertEqual(premature_event.status_code, 409, premature_event.text)
            client.post(
                f"/api/projects/{project_id}/snowflake/scene-proposals/accept",
                json={"proposal_ids": []},
            )
            accepted_event = client.put(
                f"/api/projects/{project_id}/writeback/proposals/{create_event['id']}/status",
                json={"status": "accepted"},
            )
            self.assertEqual(accepted_event.status_code, 200, accepted_event.text)
            threads = client.get(f"/api/projects/{project_id}/story-threads").json()
            self.assertEqual(len(threads), 1)
            events = client.get(
                f"/api/projects/{project_id}/story-threads/{threads[0]['id']}/events"
            ).json()
            self.assertEqual(events[0]["action"], "plant")
            self.assertTrue(events[0]["scene_id"])
        finally:
            self._cleanup(client)

    def test_accepting_a_subset_leaves_the_rest_pending(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            self._save_records(client, project_id, 8, SCENE_RECORDS)
            report = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/8/parse-scene-proposals"
            ).json()
            target = report["proposals"][0]["id"]

            accepted = client.post(
                f"/api/projects/{project_id}/snowflake/scene-proposals/accept",
                json={"proposal_ids": [target]},
            )
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(len(accepted.json()["scenes"]), 1)

            proposals = {
                item["id"]: item["status"]
                for item in client.get(
                    f"/api/projects/{project_id}/snowflake/scene-proposals"
                ).json()
            }
            self.assertEqual(proposals[target], "accepted")
            others = [status for key, status in proposals.items() if key != target]
            self.assertTrue(all(status == "pending_review" for status in others))
        finally:
            self._cleanup(client)

    def test_decided_and_unknown_proposals_map_to_409_and_404(self) -> None:
        try:
            client, _store = self._client()
            project_id = self._create_project(client)
            self._save_records(client, project_id, 8, SCENE_RECORDS)
            report = client.post(
                f"/api/projects/{project_id}/snowflake/artifacts/8/parse-scene-proposals"
            ).json()
            proposal_id = report["proposals"][0]["id"]

            rejected = client.put(
                f"/api/projects/{project_id}/snowflake/scene-proposals/{proposal_id}/status",
                json={"status": "rejected"},
            )
            self.assertEqual(rejected.status_code, 200)
            reverse = client.put(
                f"/api/projects/{project_id}/snowflake/scene-proposals/{proposal_id}/status",
                json={"status": "accepted"},
            )
            self.assertEqual(reverse.status_code, 409)

            decided_accept = client.post(
                f"/api/projects/{project_id}/snowflake/scene-proposals/accept",
                json={"proposal_ids": [proposal_id]},
            )
            self.assertEqual(decided_accept.status_code, 409)

            unknown_status = client.put(
                f"/api/projects/{project_id}/snowflake/scene-proposals/nope/status",
                json={"status": "rejected"},
            )
            self.assertEqual(unknown_status.status_code, 404)
            unknown_accept = client.post(
                f"/api/projects/{project_id}/snowflake/scene-proposals/accept",
                json={"proposal_ids": ["nope"]},
            )
            self.assertEqual(unknown_accept.status_code, 404)
        finally:
            self._cleanup(client)

    def test_project_requirement_precedes_compilation(self) -> None:
        try:
            client, _store = self._client()
            missing = client.post(
                "/api/projects/ghost-project/snowflake/artifacts/7/compile-canon-proposals"
            )
            self.assertEqual(missing.status_code, 404)
        finally:
            self._cleanup(client)


if __name__ == "__main__":
    unittest.main()
