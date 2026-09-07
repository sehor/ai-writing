import unittest

from app.snowflake.validators import (
    validate_snowflake_payload,
    validate_snowflake_record_payload,
)


VALID = {
    1: {
        "protagonist": "Mira",
        "story_goal_or_problem": "save the archive",
        "opposition_or_stakes": "the city will erase its people",
        "promise": "A cartographer must outmap a living city.",
    },
    2: {
        name: {
            "beat_id": name,
            "event": f"{name} event",
            "cause": f"{name} cause",
            "protagonist_action": f"{name} action",
            "escalation": "Raises the cost" if name in {"disaster_2", "disaster_3"} else "",
        }
        for name in ("setup", "disaster_1", "disaster_2", "disaster_3", "ending")
    },
    3: {
        "characters": [
            {
                "name": "Mira",
                "role": "protagonist",
                "one_sentence_summary": "A mapmaker.",
                "motivation": "belonging",
                "goal": "save the archive",
                "conflict": "living maps",
                "epiphany": "home can change",
                "viewpoint_summary": "Mira follows the shifting city.",
            }
        ]
    },
    4: {
        "paragraphs": [
            {"beat_id": beat, "text": f"Expanded {beat}."}
            for beat in ("setup", "disaster_1", "disaster_2", "disaster_3", "ending")
        ]
    },
    5: {
        "viewpoints": [
            {
                "character_name": "Mira",
                "character_ref": "mira",
                "viewpoint_story": "Mira sees the city change.",
                "knows": ["the map moves"],
                "does_not_know": ["who moves it"],
                "misunderstands": ["the archive is hostile"],
            }
        ]
    },
    6: {
        "blocks": [
            {
                "record_id": "act-1-sequence-1",
                "act": "Act I",
                "section": "Opening",
                "sequence": 1,
                "synopsis": "Mira reaches the archive.",
                "step4_paragraph_refs": ["setup"],
                "character_refs": ["mira"],
            }
        ]
    },
}


class SnowflakeValidatorTests(unittest.TestCase):
    def test_steps_one_through_five_accept_valid_artifact_contracts(self) -> None:
        for step, payload in VALID.items():
            if step == 6:
                continue
            with self.subTest(step=step):
                report = validate_snowflake_payload(step, "projection", payload)
                self.assertEqual(report.status, "passed", report)

    def test_step_six_blob_is_rejected_but_its_record_contract_passes(self) -> None:
        blob_report = validate_snowflake_payload(6, "projection", VALID[6])
        self.assertEqual(blob_report.status, "failed")
        self.assertEqual(blob_report.findings[0].code, "record_authority_required")

        record_report = validate_snowflake_record_payload(6, VALID[6]["blocks"][0])
        self.assertEqual(record_report.status, "passed", record_report)

    def test_all_steps_reject_missing_required_structure(self) -> None:
        for step in VALID:
            with self.subTest(step=step):
                report = validate_snowflake_payload(step, "{}\ninvalid", {})
                self.assertEqual(report.status, "failed", report)
                self.assertTrue(any(item.severity == "critical" for item in report.findings))


if __name__ == "__main__":
    unittest.main()
