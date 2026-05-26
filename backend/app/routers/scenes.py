import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.cognition.interfaces import ContextPacket, WritingScope
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store
from app.models import (
    ChapterCompileResponse,
    SceneContract,
    SceneContractCreate,
    SceneContractUpdate,
)


router = APIRouter(tags=["scenes"])


def require_project(project_id: str, data_store: WritingDataStore) -> None:
    if not data_store.project_exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )


@router.get(
    "/projects/{project_id}/scene-contracts",
    response_model=list[SceneContract],
)
def list_scene_contracts(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[SceneContract]:
    require_project(project_id, data_store)
    return data_store.list_scene_contracts(project_id)


@router.post(
    "/projects/{project_id}/scene-contracts",
    response_model=SceneContract,
    status_code=status.HTTP_201_CREATED,
)
def create_scene_contract(
    project_id: str,
    scene: SceneContractCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> SceneContract:
    require_project(project_id, data_store)
    try:
        return data_store.create_scene_contract(project_id, scene)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scene sequence already exists for this project.",
        ) from exc


@router.put(
    "/projects/{project_id}/scene-contracts/{scene_id}",
    response_model=SceneContract,
)
def update_scene_contract(
    project_id: str,
    scene_id: str,
    scene: SceneContractUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> SceneContract:
    require_project(project_id, data_store)
    try:
        updated = data_store.update_scene_contract(project_id, scene_id, scene)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scene sequence already exists for this project.",
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found.",
        )
    return updated


@router.delete(
    "/projects/{project_id}/scene-contracts/{scene_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scene_contract(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> Response:
    require_project(project_id, data_store)
    deleted = data_store.delete_scene_contract(project_id, scene_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/scene-contracts/{scene_id}/compile",
    response_model=ChapterCompileResponse,
)
def compile_scene_contract(
    project_id: str,
    scene_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> ChapterCompileResponse:
    require_project(project_id, data_store)
    scene = data_store.get_scene_contract(project_id, scene_id)
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene contract not found.",
        )

    project = data_store.get_project(project_id)
    canon_entities = data_store.list_canon_entities(project_id)
    memory_records = data_store.list_memory_records(project_id)
    artifacts = data_store.list_snowflake_artifacts(project_id)
    cognition_context = cognition.prepare_context(
        build_project_snapshot(project_id, data_store),
        WritingScope(kind="scene", ref=scene_id, instruction=scene.title),
    )
    context = build_compile_context(
        project.title if project else project_id,
        scene,
        canon_entities,
        memory_records,
        artifacts,
        cognition_context,
    )
    return ChapterCompileResponse(
        project_id=project_id,
        scene_id=scene_id,
        context=context,
        draft=build_scene_draft(scene),
        checklist=build_compile_checklist(),
    )


def build_compile_context(
    project_title: str,
    scene: SceneContract,
    canon_entities: list,
    memory_records: list,
    artifacts: list,
    cognition_context: list[ContextPacket] | None = None,
) -> str:
    source_artifact = next(
        (artifact for artifact in artifacts if artifact.step_number == scene.source_artifact_step),
        None,
    )
    canon_lines = [
        f"- {entity.entity_type}: {entity.name} | {entity.constraints or entity.current_state or entity.summary}"
        for entity in canon_entities
    ]
    memory_lines = [
        f"- {record.record_type}: {record.title} | {record.content}"
        for record in memory_records
    ]
    sections = [
        f"Project: {project_title}",
        f"Scene: {scene.sequence}. {scene.title}",
        f"POV: {scene.pov or 'TBD'}",
        f"Goal: {scene.goal or 'TBD'}",
        f"Conflict: {scene.conflict or 'TBD'}",
        f"Turning Point: {scene.turning_point or 'TBD'}",
        f"Required Canon: {scene.required_canon or 'None listed'}",
        f"Forbidden Facts: {scene.forbidden_facts or 'None listed'}",
        f"Open Threads: {scene.open_threads or 'None listed'}",
    ]
    if source_artifact:
        sections.extend(
            [
                "",
                f"Source Snowflake Step {source_artifact.step_number}:",
                source_artifact.content,
            ]
        )
    if canon_lines:
        sections.extend(["", "Loaded Canon:", "\n".join(canon_lines)])
    if memory_lines:
        sections.extend(["", "Memory / Style:", "\n".join(memory_lines)])
    if cognition_context:
        sections.extend(["", "Cognition Module Context:", format_context_packets(cognition_context)])
    return "\n".join(sections)


def build_scene_draft(scene: SceneContract) -> str:
    return "\n".join(
        [
            f"# {scene.title}",
            "",
            f"POV: {scene.pov or 'TBD'}",
            "",
            f"The scene opens with the POV pursuing this goal: {scene.goal or 'TBD'}.",
            f"Pressure rises because: {scene.conflict or 'TBD'}.",
            f"The scene turns when: {scene.turning_point or 'TBD'}.",
            "",
            "Review before committing prose to Manuscript.",
        ]
    )


def build_compile_checklist() -> list[str]:
    return [
        "POV is explicit.",
        "Scene goal, conflict, and turning point are present.",
        "Required Canon is reflected in the draft.",
        "Forbidden facts are not revealed.",
        "Memory / Style records are reflected where relevant.",
        "Open threads are advanced or intentionally deferred.",
    ]


def format_context_packets(packets: list[ContextPacket]) -> str:
    return "\n\n".join(
        "\n".join(
            [
                f"## {packet.module}: {packet.title}",
                truncate_context(packet.content, 2600),
            ]
        )
        for packet in packets
    )


def truncate_context(value: str, limit: int) -> str:
    compact = value.strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."
