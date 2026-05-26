from app.cognition.interfaces import ProjectCognitionSnapshot
from app.data import WritingDataStore


def build_project_snapshot(
    project_id: str,
    data_store: WritingDataStore,
) -> ProjectCognitionSnapshot:
    project = data_store.get_project(project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")
    return ProjectCognitionSnapshot(
        project=project,
        artifacts=data_store.list_snowflake_artifacts(project_id),
        canon_entities=data_store.list_canon_entities(project_id),
        scenes=data_store.list_scene_contracts(project_id),
        memory_records=data_store.list_memory_records(project_id),
        manuscript_scenes=data_store.list_manuscript_scenes(project_id),
    )
