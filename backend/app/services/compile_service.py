from app.errors import ResourceNotFoundError

from app.cognition.interfaces import ContextPacket
from app.cognition.registry import CognitionRegistry
from app.data.ports.reading import NarrativeSnapshotReader
from app.models import ChapterCompileResponse, SceneContract
from app.narrative import NarrativeSnapshot
from app.text_utils import truncate as truncate_context


class CompileService:
    def __init__(
        self,
        data_store: NarrativeSnapshotReader,
        cognition: CognitionRegistry,
    ):
        self.data_store = data_store
        self.cognition = cognition

    def compile_scene_contract(self, project_id: str, scene_id: str) -> ChapterCompileResponse:
        scene = self.data_store.get_scene_contract(project_id, scene_id)
        if scene is None:
            raise ResourceNotFoundError(
                detail="Scene contract not found.",
            )

        snapshot = NarrativeSnapshot.for_scene(
            project_id=project_id,
            scene_id=scene_id,
            data_store=self.data_store,
            cognition=self.cognition,
        )
        context = snapshot.render_generation_context()
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
        f"- {record.record_type}: {record.title} | {record.content}" for record in memory_records
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
        sections.extend(
            ["", "Cognition Module Context:", format_context_packets(cognition_context)]
        )
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
