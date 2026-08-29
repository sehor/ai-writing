from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.analysis.consistency import RULE_READER_KNOWLEDGE_LEAK, check_revision
from app.analysis.style import build_style_drift_report, build_style_profile
from app.cognition.graph_core import build_director_risks
from app.data import SQLiteWritingDataStore
from app.models import (
    CharacterKnowledgeCreate,
    ManuscriptRevision,
    ProjectCreate,
    SceneContractCreate,
    StoryFactCreate,
    StoryThreadCreate,
    StoryThreadEventCreate,
)


class TemporalNarrativeStateTests(unittest.TestCase):
    def test_world_reader_and_character_knowledge_have_independent_scene_boundaries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Temporal", premise="Secrets move in time."))
            fact = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="sealed letter",
                    predicate="author",
                    value="the queen",
                    valid_from_scene=10,
                    reader_visible_from=20,
                    source_ref="author:canon",
                ),
            )
            store.set_character_knowledge(
                project.id,
                fact.id,
                CharacterKnowledgeCreate(character="Mira", known_from_scene=15),
            )

            self.assertEqual(store.list_story_facts_at(project.id, 9), [])
            self.assertEqual([item.id for item in store.list_story_facts_at(project.id, 10)], [fact.id])
            self.assertEqual(store.list_reader_facts_at(project.id, 19), [])
            self.assertEqual([item.id for item in store.list_reader_facts_at(project.id, 20)], [fact.id])
            self.assertEqual(store.list_character_facts_at(project.id, "Mira", 14), [])
            self.assertEqual(
                [item.id for item in store.list_character_facts_at(project.id, "mira", 15)],
                [fact.id],
            )

    def test_fact_validity_interval_expires_old_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Intervals", premise="States change."))
            old = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="Mira",
                    predicate="location",
                    value="harbor",
                    valid_from_scene=1,
                    valid_to_scene=4,
                    reader_visible_from=1,
                ),
            )
            new = store.create_story_fact(
                project.id,
                StoryFactCreate(
                    subject="Mira",
                    predicate="location",
                    value="archive",
                    valid_from_scene=5,
                    reader_visible_from=5,
                ),
            )

            self.assertEqual([item.id for item in store.list_story_facts_at(project.id, 4)], [old.id])
            self.assertEqual([item.id for item in store.list_story_facts_at(project.id, 5)], [new.id])


class StoryThreadDirectorTests(unittest.TestCase):
    def test_director_reports_overdue_and_stalled_high_importance_thread(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Threads", premise="Promises must pay off."))
            scenes = [
                store.create_scene_contract(
                    project.id,
                    SceneContractCreate(sequence=sequence, title=f"Scene {sequence}", pov="Mira"),
                )
                for sequence in range(1, 11)
            ]
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(
                    thread_type="mystery",
                    title="Who altered the map?",
                    target_payoff_from=4,
                    target_payoff_to=6,
                    importance=5,
                    reveal_constraints="Do not name the archivist before the payoff.",
                ),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scenes[0].id, action="plant", note="Map signature differs."),
            )
            current_threads = store.list_story_threads(project.id)
            events = store.list_story_thread_events(project.id, thread.id)

            risks = build_director_risks(current_threads, events, scenes)
            titles = {risk.title for risk in risks}
            self.assertIn("Story thread payoff is overdue: Who altered the map?", titles)
            self.assertIn("Story thread has not advanced recently: Who altered the map?", titles)
            self.assertTrue(any("4-" in risk.detail or "scene 6" in risk.detail for risk in risks))
            mainline = next(
                risk
                for risk in risks
                if risk.title == "Four-scene stretch lacks high-importance thread advancement"
            )
            self.assertTrue(mainline.source_id.startswith("scene:"))
            self.assertIn(mainline.source_id.removeprefix("scene:"), {scene.id for scene in scenes})

    def test_low_importance_threads_do_not_trigger_high_importance_mainline_warning(self) -> None:
        scenes = [
            type(
                "Scene",
                (),
                {
                    "id": f"s{sequence}",
                    "sequence": sequence,
                    "conflict": "",
                    "turning_point": "",
                },
            )()
            for sequence in range(1, 5)
        ]
        thread = type(
            "Thread",
            (),
            {
                "id": "t1",
                "title": "Minor color",
                "status": "developing",
                "importance": 2,
                "target_payoff_from": None,
                "target_payoff_to": None,
                "planted_at": 1,
            },
        )()

        risks = build_director_risks([thread], [], scenes)
        self.assertFalse(
            any(
                risk.title == "Four-scene stretch lacks high-importance thread advancement"
                for risk in risks
            )
        )

    def test_payoff_event_moves_thread_to_paid_off(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteWritingDataStore(Path(temp_dir) / "app.db")
            store.init()
            project = store.create_project(ProjectCreate(title="Payoff", premise="A thread resolves."))
            scene = store.create_scene_contract(
                project.id,
                SceneContractCreate(sequence=8, title="Reveal", pov="Mira"),
            )
            thread = store.create_story_thread(
                project.id,
                StoryThreadCreate(thread_type="promise", title="Open the sealed room", importance=4),
            )
            store.add_story_thread_event(
                project.id,
                thread.id,
                StoryThreadEventCreate(scene_id=scene.id, action="payoff", note="The room opens."),
            )
            refreshed = next(item for item in store.list_story_threads(project.id) if item.id == thread.id)
            self.assertEqual(refreshed.status, "paid_off")


class StyleAndKnowledgeChecksTests(unittest.TestCase):
    def test_style_drift_is_explainable_and_does_not_rewrite_text(self) -> None:
        baseline_texts = [
            "米拉推门。风停了。她说：“进去。”\n\n灯灭了。",
            "脚步很轻。门很旧。她问：“现在？”\n\n没人回答。",
        ]
        profile = build_style_profile("p1", baseline_texts, scope="pov:Mira")
        candidate = (
            "米拉在漫长而异常复杂的走廊里缓慢地思考着所有曾经发生过的事情，"
            "因为她显然已经意识到这一切其实都来自那个无人愿意解释的秘密！！！"
            "她继续解释，因为每一个细节都必须现在说清楚！！！"
        )
        report = build_style_drift_report(
            project_id="p1",
            source_ref="revision:r3",
            profile=profile,
            text=candidate,
        )

        self.assertTrue(report.findings)
        self.assertTrue(any(item.metric == "avg_sentence_length" for item in report.findings))
        self.assertTrue(all("no rewrite is applied" in item.explanation for item in report.findings))
        self.assertEqual(candidate[-3:], "！！！")

    def test_consistency_flags_verbatim_reader_knowledge_leak(self) -> None:
        fact = type(
            "Fact",
            (),
            {
                "id": "fact-queen",
                "subject": "sealed letter",
                "predicate": "author",
                "value": "the queen",
                "valid_from_scene": 1,
                "valid_to_scene": None,
                "reader_visible_from": 5,
                "status": "confirmed",
            },
        )()
        scene = type(
            "Scene",
            (),
            {
                "sequence": 3,
                "pov": "Mira",
                "goal": "Read the letter",
                "conflict": "The seal resists",
                "turning_point": "The seal breaks",
                "required_canon": "",
                "forbidden_facts": "",
            },
        )()
        revision = ManuscriptRevision(
            id="r3",
            project_id="p1",
            scene_id="s3",
            proposal_id="p3",
            title="Scene 3",
            content="Mira reads the signature: the queen.",
            version=1,
            created_at="",
        )

        findings = check_revision(revision, scene, [], [fact])
        self.assertTrue(any(item.rule_code == RULE_READER_KNOWLEDGE_LEAK for item in findings))
        leak = next(item for item in findings if item.rule_code == RULE_READER_KNOWLEDGE_LEAK)
        self.assertEqual(leak.confidence, "exact")
        self.assertIn("scene 5", leak.expected_value)


if __name__ == "__main__":
    unittest.main()
