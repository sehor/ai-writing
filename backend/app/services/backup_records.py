"""Validate restored rows using the same readers as the live application."""

import sqlite3

from app.data.repositories.analysis import analysis_run_from_row
from app.data.repositories.generation_runs import (
    generation_attempt_from_row,
    generation_run_from_row,
)
from app.data.repositories.canon import canon_entity_from_row
from app.data.repositories.manuscript import (
    manuscript_chapter_from_row,
    manuscript_proposal_from_row,
    manuscript_revision_from_row,
    manuscript_scene_from_row,
)
from app.data.repositories.memory import memory_record_from_row
from app.data.repositories.narrative_maintenance import narrative_revision_from_row
from app.data.repositories.narrative import (
    _event_from_row,
    _fact_from_row,
    _knowledge_state_from_row,
    _relation_from_row,
    _thread_from_row,
)
from app.data.repositories.outbox import outbox_job_from_row
from app.data.repositories.projects import project_from_row
from app.data.repositories.review import reference_suggestion_from_row, writeback_proposal_from_row
from app.data.repositories.scene_proposals import scene_proposal_from_row
from app.data.repositories.scenes import scene_contract_from_row
from app.data.repositories.snowflake import artifact_from_row, head_from_row, revision_from_row
from app.data.repositories.snowflake_records import record_head_from_row, record_revision_from_row
from app.models import CharacterKnowledge


def _character_knowledge(row):
    return CharacterKnowledge.model_validate(dict(row))


RECORD_READERS = {
    "projects": project_from_row,
    "snowflake_artifacts": artifact_from_row,
    "snowflake_artifact_revisions": revision_from_row,
    "snowflake_artifact_heads": head_from_row,
    "snowflake_record_revisions": record_revision_from_row,
    "snowflake_record_heads": record_head_from_row,
    "canon_entities": canon_entity_from_row,
    "manuscript_chapters": manuscript_chapter_from_row,
    "scene_contracts": scene_contract_from_row,
    "memory_records": memory_record_from_row,
    "manuscript_proposals": manuscript_proposal_from_row,
    "manuscript_scenes": manuscript_scene_from_row,
    "manuscript_revisions": manuscript_revision_from_row,
    "writeback_proposals": writeback_proposal_from_row,
    "reference_suggestions": reference_suggestion_from_row,
    "outbox_jobs": outbox_job_from_row,
    "analysis_runs": analysis_run_from_row,
    "generation_runs": generation_run_from_row,
    "generation_attempts": generation_attempt_from_row,
    "scene_proposals": scene_proposal_from_row,
    "story_facts": _fact_from_row,
    "story_fact_character_knowledge": _character_knowledge,
    "knowledge_states": _knowledge_state_from_row,
    "narrative_revisions": narrative_revision_from_row,
    "narrative_relations": _relation_from_row,
    "story_threads": _thread_from_row,
    "story_thread_events": _event_from_row,
}


def validate_readable_records(connection: sqlite3.Connection) -> None:
    for table, read_record in RECORD_READERS.items():
        for row in connection.execute(f'SELECT * FROM "{table}"'):
            read_record(row)
