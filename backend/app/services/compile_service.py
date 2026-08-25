from fastapi import Depends, HTTPException, status

from app.cognition.interfaces import ContextPacket, WritingScope
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.cognition.snapshots import build_project_snapshot
from app.data import WritingDataStore, get_data_store
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import LlmWiki, WikiContextQuery, WikiContextResult
from app.models import ChapterCompileResponse, SceneContract
from app.text_utils import truncate as truncate_context


class CompileService:
    def __init__(
        self,
        data_store: WritingDataStore = Depends(get_data_store),
        cognition: CognitionRegistry = Depends(get_cognition_registry),
        llm_wiki: LlmWiki = Depends(get_llm_wiki),
    ):
        self.data_store = data_store
        self.cognition = cognition
        self.llm_wiki = llm_wiki

    def compile_scene_contract(self, project_id: str, scene_id: str) -> ChapterCompileResponse:
        scene = self.data_store.get_scene_contract(project_id, scene_id)
        if scene is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scene contract not found.",
            )

        project = self.data_store.get_project(project_id)
        canon_entities = self.data_store.list_canon_entities(project_id)
        memory_records = self.data_store.list_memory_records(project_id)
        artifacts = self.data_store.list_snowflake_artifacts(project_id)
        cognition_context = self.cognition.prepare_context(
            build_project_snapshot(project_id, self.data_store),
            WritingScope(kind="scene", ref=scene_id, instruction=scene.title),
        )
        llm_wiki_context = self.llm_wiki.retrieve_context(
            WikiContextQuery(
                project_id=project_id,
                snowflake_step=10,
                instruction=scene.title,
                scope=scene.id,
                story_position=scene.sequence,
                spoiler_horizon=scene.sequence,
            )
        )
        context = build_compile_context(
            project.title if project else project_id,
            scene,
            canon_entities,
            memory_records,
            artifacts,
            cognition_context,
            llm_wiki_context,
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
    llm_wiki_context: WikiContextResult | None = None,
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
        sections.extend(
            ["", "Cognition Module Context:", format_context_packets(cognition_context)]
        )
    if llm_wiki_context and llm_wiki_context.evidence:
        sections.extend(
            [
                "",
                "LLM Wiki Context:",
                format_llm_wiki_evidence(llm_wiki_context),
            ]
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


def format_llm_wiki_evidence(context: WikiContextResult) -> str:
    return "\n\n".join(
        "\n".join(
            [
                f"## {evidence.title}",
                f"Source: {evidence.source_ref}",
                truncate_context(evidence.excerpt, 2600),
            ]
        )
        for evidence in context.evidence
    )
