"""Legacy cognition snapshot helpers.

Scene-scoped narrative context now lives in :mod:`app.narrative.snapshot`.
This module keeps the historical import path and project-wide cognition snapshot
builder for consumers that have not moved to scene-scoped context.
"""

from app.cognition.interfaces import ProjectCognitionSnapshot
from app.data.ports.reading import ProjectSnapshotReader
from app.narrative.snapshot import NarrativeSnapshot


def build_project_snapshot(
    project_id: str,
    data_store: ProjectSnapshotReader,
) -> ProjectCognitionSnapshot:
    project = data_store.get_project(project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")
    story_threads = data_store.list_story_threads(project_id)
    story_thread_events = [
        event
        for thread in story_threads
        for event in data_store.list_story_thread_events(project_id, thread.id)
    ]
    return ProjectCognitionSnapshot(
        project=project,
        artifacts=data_store.list_snowflake_artifacts(project_id),
        canon_entities=data_store.list_canon_entities(project_id),
        scenes=data_store.list_scene_contracts(project_id),
        memory_records=data_store.list_memory_records(project_id),
        manuscript_scenes=data_store.list_manuscript_scenes(project_id),
        story_threads=story_threads,
        story_thread_events=story_thread_events,
    )


__all__ = ["NarrativeSnapshot", "build_project_snapshot"]
