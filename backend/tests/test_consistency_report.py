"""P1-06: deterministic consistency report rules, idempotency, and routes."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.analysis.consistency import (
    RULE_CONSTRAINT_CAPABILITY_USED,
    RULE_FORBIDDEN_FACT_MENTION,
    RULE_POV_NAME_ABSENT,
    RULE_REQUIRED_CANON_MISSING,
    check_revision,
)
from app.data import SQLiteWritingDataStore, get_data_store
from app.main import app
from app.models import CanonEntity, ManuscriptProposalCreate, ManuscriptRevision, SceneContract
from _polling import wait_until


def _make_revision(content: str) -> ManuscriptRevision:
    return ManuscriptRevision(
        id="rev-1",
        project_id="p1",
        scene_id="scene-1",
        proposal_id="prop-1",
        title="Revision",
        content=content,
        version=1,
        created_at="",
    )


def _make_scene(**overrides) -> SceneContract:
    fields = dict(
        id="scene-1",
        project_id="p1",
        sequence=1,
        title="Archive Threshold",
        pov="Mira",
        goal="Enter the archive.",
        conflict="The map refuses the door.",
        turning_point="The map redraws itself.",
        required_canon="Mira; the Iron Key",
        forbidden_facts="the archive burned down",
    )
    fields.update(overrides)
    return SceneContract(**fields)


def _make_canon() -> list[CanonEntity]:
    return [
        CanonEntity(
            id="canon-mira",
            project_id="p1",
            entity_type="character",
            name="Mira",
            summary="Archivist.",
        ),
        CanonEntity(
            id="canon-key",
            project_id="p1",
            entity_type="item",
            name="the Iron Key",
            summary="Opens the lower door.",
        ),
    ]


class ConsistencyRuleTests(unittest.TestCase):
    """Deterministic rules produce evidence-backed findings only when hit."""

    def test_forbidden_fact_mention_is_critical_with_excerpt(self) -> None:
        revision = _make_revision('Mira said, "the archive burned down that night," and left.')
        scene = _make_scene(required_canon="Mira")
        findings = check_revision(revision, scene, _make_canon())

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule_code, RULE_FORBIDDEN_FACT_MENTION)
        self.assertEqual(finding.severity, "critical")
        self.assertEqual(finding.confidence, "exact")
        self.assertIn("the archive burned down", finding.manuscript_excerpt)

    def test_clean_revision_produces_no_findings(self) -> None:
        revision = _make_revision("Mira tightened her grip on the Iron Key and stepped forward.")
        findings = check_revision(revision, _make_scene(), _make_canon())

        self.assertEqual(findings, [])

    def test_missing_required_canon_is_reported(self) -> None:
        revision = _make_revision("Mira walked the corridor alone.")
        findings = check_revision(revision, _make_scene(), _make_canon())

        missing = [item for item in findings if item.rule_code == RULE_REQUIRED_CANON_MISSING]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].severity, "warning")
        self.assertEqual(missing[0].canon_entity_id, "canon-key")

    def test_forbidden_constraint_capability_in_prose_is_flagged(self) -> None:
        canon = _make_canon()
        canon[0].constraints = "不能使用暗影魔法"
        revision = _make_revision("Mira used 暗影魔法 to slip past the gate.")
        findings = check_revision(revision, _make_scene(), canon)

        used = [item for item in findings if item.rule_code == RULE_CONSTRAINT_CAPABILITY_USED]
        self.assertEqual(len(used), 1)
        self.assertEqual(used[0].severity, "warning")
        self.assertEqual(used[0].confidence, "heuristic")
        self.assertIn("暗影魔法", used[0].manuscript_excerpt)

    def test_absent_pov_name_is_info_finding(self) -> None:
        scene = _make_scene(pov="Rowan")
        revision = _make_revision("Mira counted the shelves twice.")
        findings = check_revision(revision, scene, _make_canon())

        pov = [item for item in findings if item.rule_code == RULE_POV_NAME_ABSENT]
        self.assertEqual(len(pov), 1)
        self.assertEqual(pov[0].severity, "info")

    def test_present_pov_name_produces_no_finding(self) -> None:
        revision = _make_revision("Mira counted the shelves twice.")
        findings = check_revision(revision, _make_scene(), _make_canon())

        pov = [item for item in findings if item.rule_code == RULE_POV_NAME_ABSENT]
        self.assertEqual(pov, [])


class ConsistencyReportRouteTests(unittest.TestCase):
    """POST runs once per input; GET replays the latest stored report."""

    PROSE = 'Mira held the Iron Key. "the archive burned down that night," she said.'

    def _setup(self, store: SQLiteWritingDataStore, client: TestClient) -> tuple[str, str]:
        project_id = client.post(
            "/api/projects",
            json={"title": "Consistent Novel", "premise": "Checked before trusted."},
        ).json()["id"]
        scene = client.post(
            f"/api/projects/{project_id}/scene-contracts",
            json={
                "sequence": 1,
                "title": "Archive Threshold",
                "pov": "Mira",
                "goal": "Enter the archive.",
                "required_canon": "Mira; the Iron Key",
                "forbidden_facts": "the archive burned down",
                "source_artifact_step": 8,
            },
        ).json()
        client.post(
            f"/api/projects/{project_id}/canon/entities",
            json={"entity_type": "character", "name": "Mira"},
        )
        client.post(
            f"/api/projects/{project_id}/canon/entities",
            json={"entity_type": "item", "name": "the Iron Key"},
        )
        proposal = store.create_manuscript_proposal(
            project_id,
            ManuscriptProposalCreate(
                scene_id=scene["id"],
                title="1. Archive Threshold",
                content=self.PROSE,
                context="Compiled context.",
            ),
        )
        accepted = client.put(
            f"/api/projects/{project_id}/manuscript/proposals/{proposal.id}/status",
            json={"status": "accepted"},
        )
        assert accepted.status_code == 200
        revision = store.list_manuscript_revisions(project_id)[0]
        return project_id, revision.id

    def _post_report(self, client: TestClient, project_id: str, revision_id: str, **params):
        return client.post(
            f"/api/projects/{project_id}/analysis/consistency/from-revision/{revision_id}",
            params=params,
        )

    def _wait_for_automatic_consistency_run(
        self, store: SQLiteWritingDataStore, project_id: str
    ) -> None:
        """P1-03: the acceptance-time report is produced by the dispatcher."""
        wait_until(
            lambda: [
                job
                for job in store.list_outbox_jobs(project_id, job_status="succeeded")
                if job.job_type == "consistency_analysis"
            ],
            timeout_seconds=20,
            message="automatic consistency job to succeed",
        )

    def test_report_exists_after_acceptance_and_force_bumps_version(self) -> None:
        """P1-07: acceptance produces a report without a manual trigger."""
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, revision_id = self._setup(store, client)
                    self._wait_for_automatic_consistency_run(store, project_id)

                    automatic = client.get(
                        f"/api/projects/{project_id}/analysis/consistency"
                        f"/from-revision/{revision_id}"
                    )
                    first = self._post_report(client, project_id, revision_id)
                    forced = self._post_report(client, project_id, revision_id, force=True)
                    latest = client.get(
                        f"/api/projects/{project_id}/analysis/consistency"
                        f"/from-revision/{revision_id}"
                    )
                    runs = [
                        run
                        for run in store.list_analysis_runs(project_id)
                        if run.processor == "consistency_checker"
                    ]
            finally:
                app.dependency_overrides.clear()

        # The report already exists before anybody asked for it.
        self.assertEqual(automatic.status_code, 200)
        body = automatic.json()
        self.assertEqual(body["summary"]["finding_count"], 1)
        self.assertEqual(body["summary"]["critical_count"], 1)
        self.assertEqual(body["findings"][0]["rule_code"], RULE_FORBIDDEN_FACT_MENTION)
        self.assertIn("the archive burned down", body["findings"][0]["manuscript_excerpt"])

        # An unchanged manual request replays the automatic run.
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["cached"])
        self.assertEqual(first.headers.get("X-Analysis-Cached"), "true")
        self.assertEqual(first.headers.get("X-Analysis-Run-Id"), body["run_id"])

        self.assertEqual(forced.headers.get("X-Analysis-Run-Version"), "2")
        self.assertEqual(forced.json()["summary"]["finding_count"], 1)

        # GET returns the newest stored state (post-force run v2).
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["run_version"], 2)
        self.assertEqual(len(runs), 1, "same input stays on one run row")
        self.assertEqual(runs[0].processor, "consistency_checker")

    def test_changed_inputs_generate_a_fresh_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, revision_id = self._setup(store, client)
                    self._wait_for_automatic_consistency_run(store, project_id)

                    first = self._post_report(client, project_id, revision_id)
                    scene_id = client.get(f"/api/projects/{project_id}/scene-contracts").json()[0][
                        "id"
                    ]
                    client.put(
                        f"/api/projects/{project_id}/scene-contracts/{scene_id}",
                        json={
                            "sequence": 1,
                            "title": "Archive Threshold",
                            "pov": "Mira",
                            "required_canon": "Mira; the Iron Key",
                            "forbidden_facts": "nothing is forbidden now",
                            "source_artifact_step": 8,
                        },
                    )
                    second = self._post_report(client, project_id, revision_id)
                    runs = [
                        run
                        for run in store.list_analysis_runs(project_id)
                        if run.processor == "consistency_checker"
                    ]
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            second.headers.get("X-Analysis-Run-Id"),
            first.headers.get("X-Analysis-Run-Id"),
        )
        self.assertFalse(second.json()["cached"])
        self.assertEqual(second.json()["summary"]["finding_count"], 0)
        self.assertEqual(len(runs), 2)

    def test_unknown_revision_and_project_return_404(self) -> None:
        """Unknown sources stay 404; accepted revisions have a report (P1-07)."""
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            app.dependency_overrides[get_data_store] = lambda: store
            try:
                with TestClient(app) as client:
                    project_id, revision_id = self._setup(store, client)

                    existing = client.get(
                        f"/api/projects/{project_id}/analysis/consistency"
                        f"/from-revision/{revision_id}"
                    )
                    unknown_revision = client.get(
                        f"/api/projects/{project_id}/analysis/consistency/from-revision/nope"
                    )
                    unknown_project = self._post_report(client, "ghost", revision_id)
            finally:
                app.dependency_overrides.clear()

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(unknown_revision.status_code, 404)
        self.assertEqual(unknown_project.status_code, 404)


if __name__ == "__main__":
    unittest.main()
