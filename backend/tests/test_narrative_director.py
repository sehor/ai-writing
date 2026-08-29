from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.data import SQLiteWritingDataStore
from app.models import (
    ManuscriptProposalCreate,
    NarrativeRelationCreate,
    ProjectCreate,
    SceneContractCreate,
    StoryFactCreate,
    StoryThreadCreate,
    StoryThreadEventCreate,
    StoryThreadStatusUpdate,
)
from app.narrative import NarrativeGraphProjector, NarrativeSnapshot
from app.narrative.director import DirectorAnalyzer


class NarrativeDirectorLifecycleTests(unittest.TestCase):
    def _create_project(self, temp_dir: str, scene_count: int = 10):
        root = Path(temp_dir)
        store = SQLiteWritingDataStore(root / "app.db")
        store.init()
        project = store.create_project(
            ProjectCreate(
                title="Director Analytics",
                premise="Structured threads are analyzed at scene boundaries.",
            )
        )
        scenes = [
            store.create_scene_contract(
                project.id,
                SceneContractCreate(
                    sequence=sequence,
                    title=f"Scene {sequence}",
                    pov="Mira",
                ),
            )
            for sequence in range(1, scene_count + 1)
        ]
        return root, store, project, scenes

    def _lifecycle(self, report, thread_id: str):
        return next(item for item in report.thread_lifecycles if item.thread_id == thread_id)

    def _findings(self, report, code: str):
        return [item for item in report.findings if item.code == code]

    def test_scene_analysis_rebuilds_history_and_ignores_future_payoff(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir)
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="mystery",
                    title="Who altered the map?",
                    target_payoff_from=4,
                    target_payoff_to=5,
                    importance=5,
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(
                    scene_id=scenes[0].id,
                    action="plant",
                    note="The signature differs.",
                ),
            )
            reinforce = store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(
                    scene_id=scenes[2].id,
                    action="reinforce",
                    note="The ink matches a hidden ledger.",
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(
                    scene_id=scenes[8].id,
                    action="payoff",
                    note="The forger is exposed later.",
                ),
            )
            self.assertEqual(store.list_story_threads(project.id)[0].status, "paid_off")

            analyzer = DirectorAnalyzer(store)
            first = analyzer.for_scene(project_id=project.id, scene_id=scenes[6].id)
            second = analyzer.for_scene(project_id=project.id, scene_id=scenes[6].id)
            snapshot = NarrativeSnapshot.for_scene(
                project_id=project.id,
                scene_id=scenes[6].id,
                data_store=store,
            )
            graph = NarrativeGraphProjector(store).project(project.id)
            rebuilt = analyzer.analyze_scene(snapshot, graph)

            self.assertEqual(first, second)
            self.assertEqual(first, rebuilt)
            lifecycle = self._lifecycle(first, thread.id)
            self.assertEqual(lifecycle.status, "developing")
            self.assertEqual(lifecycle.database_status, "paid_off")
            self.assertTrue(lifecycle.history_exact)
            self.assertEqual(lifecycle.last_event_id, reinforce.id)
            self.assertNotIn("payoff", [event.action for event in snapshot.story_thread_events])

            overdue = self._findings(first, "DIRECTOR_PAYOFF_OVERDUE")
            self.assertEqual(len(overdue), 1)
            self.assertEqual(overdue[0].severity, "critical")
            self.assertEqual(overdue[0].data["current_scene"], 7)
            self.assertEqual(overdue[0].data["target_payoff_to"], 5)
            self.assertEqual(overdue[0].data["last_progress_scene"], 3)
            self.assertEqual(overdue[0].data["overdue_by"], 2)
            self.assertEqual(overdue[0].evidence[0].ref, reinforce.id)

    def test_planned_and_planted_lifecycle_are_rebuilt_from_scene_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir, scene_count=6)
            planned = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="promise",
                    title="A future promise",
                    planted_at=5,
                    importance=3,
                ),
            )
            planted = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="mystery",
                    title="The missing key",
                    importance=3,
                ),
            )
            store.add_story_thread_event(
                project.id,
                planted.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )

            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[2].id,
            )

            self.assertEqual(self._lifecycle(report, planned.id).status, "planned")
            self.assertEqual(self._lifecycle(report, planted.id).status, "planted")

    def test_payoff_due_at_window_end_is_reported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir, scene_count=6)
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="promise",
                    title="Deliver the warning",
                    target_payoff_from=3,
                    target_payoff_to=5,
                    importance=4,
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )

            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[4].id,
            )

            overdue = self._findings(report, "DIRECTOR_PAYOFF_OVERDUE")
            self.assertEqual(len(overdue), 1)
            self.assertEqual(overdue[0].data["overdue_by"], 0)

    def test_premature_payoff_has_scene_and_event_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir)
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="promise",
                    title="Open the sealed room",
                    target_payoff_from=6,
                    target_payoff_to=8,
                    importance=4,
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )
            payoff = store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(
                    scene_id=scenes[2].id,
                    action="payoff",
                    note="The room opens too soon.",
                ),
            )

            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[6].id,
            )

            lifecycle = self._lifecycle(report, thread.id)
            self.assertEqual(lifecycle.status, "paid_off")
            premature = self._findings(report, "DIRECTOR_PREMATURE_PAYOFF")
            self.assertEqual(len(premature), 1)
            self.assertEqual(premature[0].data["actual_payoff_scene"], 3)
            self.assertEqual(premature[0].data["target_payoff_from"], 6)
            self.assertEqual(premature[0].data["early_by"], 3)
            self.assertEqual(premature[0].evidence[0].ref, payoff.id)
            self.assertEqual(premature[0].evidence[0].scene_sequence, 3)
            self.assertEqual(self._findings(report, "DIRECTOR_PAYOFF_OVERDUE"), [])

    def test_dormant_stalled_threshold_is_deterministic_and_importance_aware(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir)
            minor = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="subplot",
                    title="A minor rivalry",
                    importance=2,
                ),
            )
            major = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="conflict",
                    title="The succession struggle",
                    importance=5,
                ),
            )
            for thread in (minor, major):
                store.add_story_thread_event(
                    project.id,
                    thread.id,
                    StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
                )
                store.add_story_thread_event(
                    project.id,
                    thread.id,
                    StoryThreadEventCreate(scene_id=scenes[1].id, action="reinforce"),
                )

            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[7].id,
            )

            self.assertEqual(self._lifecycle(report, minor.id).status, "dormant")
            self.assertEqual(self._lifecycle(report, major.id).status, "dormant")
            stalled = self._findings(report, "DIRECTOR_THREAD_STALLED")
            by_thread = {finding.thread_ids[0]: finding for finding in stalled}
            self.assertEqual(by_thread[minor.id].severity, "info")
            self.assertEqual(by_thread[major.id].severity, "warning")
            self.assertEqual(by_thread[minor.id].data["inactive_scenes"], 6)
            self.assertEqual(by_thread[minor.id].data["threshold"], 5)

    def test_normal_payoff_is_not_overdue(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir)
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="relationship",
                    title="Mira trusts Chen",
                    target_payoff_from=3,
                    target_payoff_to=5,
                    importance=4,
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[3].id, action="payoff"),
            )

            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[7].id,
            )

            self.assertEqual(self._lifecycle(report, thread.id).status, "paid_off")
            self.assertEqual(self._findings(report, "DIRECTOR_PAYOFF_OVERDUE"), [])
            self.assertEqual(self._findings(report, "DIRECTOR_PREMATURE_PAYOFF"), [])

    def test_manual_abandonment_is_not_backdated_without_a_timestamp(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir, scene_count=8)
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="subplot",
                    title="The dockworkers organize",
                    importance=3,
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[1].id, action="reinforce"),
            )
            store.update_story_thread_status(
                project.id,
                thread.id,
                StoryThreadStatusUpdate(status="abandoned"),
            )

            historical = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[4].id,
            )
            current = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[7].id,
            )

            historical_lifecycle = self._lifecycle(historical, thread.id)
            self.assertEqual(historical_lifecycle.status, "developing")
            self.assertEqual(historical_lifecycle.database_status, "abandoned")
            self.assertIn("not backdated", historical_lifecycle.detail)
            current_lifecycle = self._lifecycle(current, thread.id)
            self.assertEqual(current_lifecycle.status, "abandoned")
            self.assertFalse(current_lifecycle.history_exact)
            self.assertEqual(current_lifecycle.status_basis, "current_status")


class NarrativeDirectorGraphTests(unittest.TestCase):
    def _create_project(self, temp_dir: str):
        root = Path(temp_dir)
        store = SQLiteWritingDataStore(root / "app.db")
        store.init()
        project = store.create_project(
            ProjectCreate(title="Director Graph", premise="Structure is advisory, not authority.")
        )
        scenes = [
            store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=sequence, title=f"Scene {sequence}", pov="Mira"),
            )
            for sequence in range(1, 7)
        ]
        return root, store, project, scenes

    def test_isolated_thread_is_reported_but_connected_thread_is_not(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir)
            isolated = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="mystery",
                    title="The unsigned warning",
                    importance=4,
                ),
            )
            connected = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="conflict",
                    title="Mira confronts the council",
                    importance=5,
                ),
            )
            isolated_event = store.add_story_thread_event(
                project.id,
                isolated.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )
            connected_event = store.add_story_thread_event(
                project.id,
                connected.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )
            store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source=f"thread:{connected.id}",
                    target=f"event:{connected_event.id}",
                    relation="PLANTED_AT",
                    valid_from=1,
                    source_ref=connected_event.id,
                ),
            )
            store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source=f"event:{connected_event.id}",
                    target="character:mira",
                    relation="AFFECTS",
                    valid_from=1,
                    source_ref=connected_event.id,
                ),
            )

            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[3].id,
            )
            isolated_findings = [
                item for item in report.findings if item.code == "DIRECTOR_ISOLATED_THREAD"
            ]

            self.assertEqual([item.thread_ids[0] for item in isolated_findings], [isolated.id])
            self.assertIn(f"event:{isolated_event.id}", isolated_findings[0].node_ids)
            self.assertFalse(
                any(
                    item.code in {"DIRECTOR_ISOLATED_THREAD", "DIRECTOR_CAUSAL_CHAIN_WEAK"}
                    and connected.id in item.thread_ids
                    for item in report.findings
                )
            )

    def test_future_relation_does_not_connect_past_scene(self) -> None:
        with TemporaryDirectory() as temp_dir:
            _, store, project, scenes = self._create_project(temp_dir)
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(thread_type="promise", title="Recover the ledger", importance=4),
            )
            event = store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )
            store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source=f"thread:{thread.id}",
                    target=f"event:{event.id}",
                    relation="REFERENCES",
                    valid_from=6,
                    source_ref=event.id,
                ),
            )

            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[3].id,
            )

            isolated = [item for item in report.findings if item.code == "DIRECTOR_ISOLATED_THREAD"]
            self.assertEqual(len(isolated), 1)
            self.assertEqual(isolated[0].thread_ids, (thread.id,))

    def test_community_is_advisory_and_analysis_does_not_mutate_authority(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root, store, project, scenes = self._create_project(temp_dir)
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="relationship",
                    title="Mira and Chen form an alliance",
                    importance=4,
                ),
            )
            event = store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant"),
            )
            fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="Mira",
                    predicate="trusts",
                    value="Chen",
                    valid_from_scene=1,
                    reader_visible_from=1,
                ),
            )
            relation = store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source=f"thread:{thread.id}",
                    target=f"event:{event.id}",
                    relation="PLANTED_AT",
                    valid_from=1,
                    source_ref=event.id,
                ),
            )
            store.create_narrative_relation(
                project.id,
                NarrativeRelationCreate(
                    source=f"event:{event.id}",
                    target="character:mira",
                    relation="CHANGES_STATE",
                    valid_from=1,
                    source_ref=event.id,
                ),
            )
            proposal = store.create_manuscript_proposal(
                project.id,
                ManuscriptProposalCreate(
                    scene_id=scenes[0].id,
                    title=scenes[0].title,
                    content="Mira accepts Chen's help.",
                ),
            )
            store.accept_manuscript_proposal(project.id, proposal.id)

            before = {
                "threads": store.list_story_threads(project.id),
                "facts": store.list_story_facts(project.id),
                "relations": store.list_narrative_relations(project.id),
                "manuscript": store.list_manuscript_scenes(project.id),
            }
            report = DirectorAnalyzer(store).for_scene(
                project_id=project.id,
                scene_id=scenes[3].id,
            )
            after = {
                "threads": store.list_story_threads(project.id),
                "facts": store.list_story_facts(project.id),
                "relations": store.list_narrative_relations(project.id),
                "manuscript": store.list_manuscript_scenes(project.id),
            }

            self.assertEqual(before, after)
            self.assertEqual(before["facts"][0].id, fact.id)
            self.assertIn(relation.id, {item.id for item in before["relations"]})
            self.assertTrue(report.communities)
            self.assertTrue(
                all("does not define an Arc" in item.detail for item in report.communities)
            )
            community_findings = [
                item
                for item in report.findings
                if item.code == "DIRECTOR_GRAPH_COMMUNITY_SUGGESTION"
            ]
            self.assertTrue(community_findings)
            self.assertTrue(all(item.advisory for item in community_findings))
            derived_files = [
                path
                for path in root.rglob("*")
                if path.is_file()
                and any(token in path.name.lower() for token in ("director", "graph"))
            ]
            self.assertEqual(derived_files, [])


if __name__ == "__main__":
    unittest.main()
