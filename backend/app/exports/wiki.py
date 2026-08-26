"""Obsidian-compatible Markdown export of a project's committed state.

Moved here from ``app.cognition.llm_wiki`` (P2-05): this module owns the
Markdown exporter only. Runtime wiki ingestion / retrieval lives behind
``app.llm_wiki.interfaces``; nothing in this package writes back into app
state.
"""

import json
from pathlib import Path

from app.cognition.graph_core import build_graph_edges, build_graph_nodes, build_graph_risks
from app.data import utc_now
from app.models import (
    CanonEntity,
    MemoryRecord,
    ManuscriptScene,
    ProjectSummary,
    SceneContract,
    SnowflakeArtifact,
    WikiExportFile,
    WikiExportResponse,
)
from app.text_utils import one_line, slug_with_id, slugify

__all__ = [
    "WikiPaths",
    "build_wiki_export",
    "persist_export",
    "safe_child_path",
    "wiki_file",
]


def build_wiki_export(
    project: ProjectSummary,
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
    manuscript_scenes: list[ManuscriptScene],
) -> WikiExportResponse:
    generated_at = utc_now()
    paths = WikiPaths(project, artifacts, canon_entities, scenes, memory_records, manuscript_scenes)
    files = [
        wiki_file("SCHEMA.md", build_schema(project)),
        wiki_file("index.md", build_index(project, generated_at, paths)),
        wiki_file("log.md", build_log(generated_at, paths)),
        wiki_file("project.md", build_project_page(project, paths)),
    ]
    files.extend(
        wiki_file(paths.artifact_path(artifact), build_artifact_page(artifact, paths))
        for artifact in artifacts
    )
    files.extend(
        wiki_file(paths.entity_path(entity), build_entity_page(entity, scenes, paths))
        for entity in canon_entities
    )
    files.extend(
        wiki_file(paths.memory_path(record), build_memory_page(record, paths))
        for record in memory_records
    )
    files.extend(
        wiki_file(
            paths.scene_path(scene), build_scene_page(scene, canon_entities, memory_records, paths)
        )
        for scene in scenes
    )
    files.extend(
        wiki_file(paths.manuscript_scene_path(scene.scene_id), build_manuscript_page(scene, paths))
        for scene in manuscript_scenes
        if paths.manuscript_scene_path(scene.scene_id)
    )
    files.append(
        wiki_file(
            "graph.md",
            build_graph_page(project, artifacts, canon_entities, scenes, memory_records),
        )
    )
    files.append(
        WikiExportFile(
            path="raw/project-state.json",
            content_type="application/json",
            content=build_state_snapshot(
                project,
                artifacts,
                canon_entities,
                scenes,
                memory_records,
                manuscript_scenes,
                generated_at,
            ),
        )
    )
    return WikiExportResponse(
        project_id=project.id,
        title=project.title,
        file_count=len(files),
        generated_at=generated_at,
        files=files,
    )


def persist_export(project_path: Path, export: WikiExportResponse) -> None:
    project_path.mkdir(parents=True, exist_ok=True)
    for file in export.files:
        target = safe_child_path(project_path, file.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.content, encoding="utf-8")


def safe_child_path(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if resolved_root != target and resolved_root not in target.parents:
        raise ValueError(f"Unsafe module path: {relative_path}")
    return target


class WikiPaths:
    def __init__(
        self,
        project: ProjectSummary,
        artifacts: list[SnowflakeArtifact],
        canon_entities: list[CanonEntity],
        scenes: list[SceneContract],
        memory_records: list[MemoryRecord],
        manuscript_scenes: list[ManuscriptScene],
    ) -> None:
        self.project = project
        self.artifacts = artifacts
        self.canon_entities = canon_entities
        self.scenes = scenes
        self.memory_records = memory_records
        self.manuscript_scenes = manuscript_scenes

    def artifact_path(self, artifact: SnowflakeArtifact) -> str:
        return f"artifacts/step-{artifact.step_number}-{slugify(artifact.artifact)}.md"

    def entity_path(self, entity: CanonEntity) -> str:
        return f"entities/{entity.entity_type}-{slug_with_id(entity.name, entity.id)}.md"

    def memory_path(self, record: MemoryRecord) -> str:
        return f"memory/{record.record_type}-{slug_with_id(record.title, record.id)}.md"

    def scene_path(self, scene: SceneContract) -> str:
        return f"scenes/{scene.sequence:03d}-{slug_with_id(scene.title, scene.id)}.md"

    def manuscript_scene_path(self, scene_id: str) -> str:
        manuscript_scene = next(
            (scene for scene in self.manuscript_scenes if scene.scene_id == scene_id),
            None,
        )
        if manuscript_scene is None:
            return ""
        source_scene = next((scene for scene in self.scenes if scene.id == scene_id), None)
        if source_scene is None:
            return f"manuscript/{slug_with_id(manuscript_scene.title, manuscript_scene.id)}.md"
        return f"manuscript/{source_scene.sequence:03d}-{slug_with_id(manuscript_scene.title, manuscript_scene.id)}.md"

    def link(self, path: str, label: str) -> str:
        target = path[:-3] if path.endswith(".md") else path
        return f"[[{target}|{escape_link_label(label)}]]"


def wiki_file(path: str, content: str) -> WikiExportFile:
    return WikiExportFile(
        path=path,
        content_type="text/markdown",
        content=content.strip() + "\n",
    )


def build_schema(project: ProjectSummary) -> str:
    return "\n".join(
        [
            "# Wiki Schema",
            "",
            "## Domain",
            f"This wiki is an exported knowledge layer for the fiction project **{project.title}**.",
            "It compiles Snowflake planning, confirmed Canon, Memory / Style records, Scene Contracts, manuscript state, and structure analysis into Obsidian-compatible Markdown.",
            "",
            "## Layers",
            "- `raw/project-state.json` is the immutable export snapshot for this package.",
            "- Markdown pages are compiled knowledge pages derived from the snapshot.",
            "- This schema defines how an agent should maintain future exports or imported copies.",
            "",
            "## Conventions",
            "- Use `[[wikilinks]]` between project, artifact, entity, memory, scene, and graph pages.",
            "- Canon entity pages are confirmed story facts, not ordinary notes.",
            "- Memory pages preserve prose continuity, voice, rhythm, and summaries, not fact correctness.",
            "- Scene pages link to their source Snowflake artifact and named Canon entities.",
            "- Contradictions or uncertain changes should become reviewable write-back proposals before state is committed.",
            "- Do not edit files under `raw/`; generate a fresh export from the app state instead.",
            "",
            "## Page Types",
            "- `project`: project overview and navigation hub.",
            "- `snowflake_artifact`: planning source pages.",
            "- `canon_entity`: confirmed characters, locations, items, factions, and rules.",
            "- `memory_record`: continuity and style records.",
            "- `scene`: structured scene contracts and linked accepted manuscript state.",
            "- `manuscript_scene`: accepted manuscript prose pages.",
            "- `graph`: structure analysis, relationship edges, and risks.",
            "",
            "## Maintenance Policy",
            "- Read `index.md` first when answering questions.",
            "- Use `log.md` to understand when the export was generated.",
            "- Prefer updating the app database through reviewed write-back workflows over hand-editing exported pages.",
            "- If hand-edited pages are imported later, reconcile them against Canon and preserve provenance.",
        ]
    )


def build_index(project: ProjectSummary, generated_at: str, paths: WikiPaths) -> str:
    total_pages = (
        5
        + len(paths.artifacts)
        + len(paths.canon_entities)
        + len(paths.scenes)
        + len(paths.memory_records)
        + len(paths.manuscript_scenes)
    )
    sections = [
        "# Wiki Index",
        "",
        "> Content catalog for the exported project wiki.",
        f"> Last generated: {generated_at} | Total markdown pages: {total_pages}",
        "",
        "## Project",
        f"- {paths.link('project.md', project.title)} - project overview and navigation hub.",
        f"- {paths.link('graph.md', 'Graph / Structure')} - structure edges, risks, and gap report.",
        "",
        "## Snowflake Artifacts",
    ]
    sections.extend(
        f"- {paths.link(paths.artifact_path(artifact), f'Step {artifact.step_number}: {artifact.artifact}')} - planning source."
        for artifact in paths.artifacts
    )
    sections.extend(["", "## Canon Entities"])
    sections.extend(
        f"- {paths.link(paths.entity_path(entity), entity.name)} - {entity.entity_type}; {one_line(entity.summary or entity.current_state)}"
        for entity in paths.canon_entities
    )
    sections.extend(["", "## Memory / Style"])
    sections.extend(
        f"- {paths.link(paths.memory_path(record), record.title)} - {record.record_type}; {one_line(record.scope or record.tags)}"
        for record in paths.memory_records
    )
    sections.extend(["", "## Scenes"])
    sections.extend(
        f"- {paths.link(paths.scene_path(scene), f'{scene.sequence}. {scene.title}')} - POV: {scene.pov or 'unset'}."
        for scene in paths.scenes
    )
    sections.extend(["", "## Accepted Manuscript"])
    sections.extend(
        f"- {paths.link(paths.manuscript_scene_path(scene.scene_id), scene.title)} - version {scene.version}."
        for scene in paths.manuscript_scenes
        if paths.manuscript_scene_path(scene.scene_id)
    )
    return "\n".join(sections)


def build_log(generated_at: str, paths: WikiPaths) -> str:
    return "\n".join(
        [
            "# Wiki Log",
            "",
            "> Chronological record of exported wiki actions.",
            "",
            f"## [{generated_at}] export | {paths.project.title}",
            f"- Exported {len(paths.artifacts)} Snowflake artifacts.",
            f"- Exported {len(paths.canon_entities)} Canon entity pages.",
            f"- Exported {len(paths.memory_records)} Memory / Style pages.",
            f"- Exported {len(paths.scenes)} Scene Contract pages.",
            f"- Exported {len(paths.manuscript_scenes)} accepted manuscript scene pages.",
            "- Exported Graph / Structure analysis and raw project-state snapshot.",
        ]
    )


def build_project_page(project: ProjectSummary, paths: WikiPaths) -> str:
    return page(
        "Project",
        "project",
        ["project", "fiction", "snowflake"],
        [
            f"# {project.title}",
            "",
            "## Premise",
            project.premise,
            "",
            "## Navigation",
            f"- {paths.link('index.md', 'Wiki Index')}",
            f"- {paths.link('graph.md', 'Graph / Structure')}",
            f"- Snowflake artifacts: {len(paths.artifacts)}",
            f"- Canon entities: {len(paths.canon_entities)}",
            f"- Memory / Style records: {len(paths.memory_records)}",
            f"- Scene contracts: {len(paths.scenes)}",
            "",
            "## Current State",
            f"- Current Snowflake step: {project.current_step}",
            "- Source snapshot: `raw/project-state.json`",
        ],
    )


def build_artifact_page(artifact: SnowflakeArtifact, paths: WikiPaths) -> str:
    return page(
        f"Step {artifact.step_number}: {artifact.artifact}",
        "snowflake_artifact",
        ["snowflake", artifact.artifact],
        [
            f"# Step {artifact.step_number}: {artifact.artifact}",
            "",
            f"Project: {paths.link('project.md', paths.project.title)}",
            "",
            "## Content",
            artifact.content,
            "",
            "## Referenced By Scenes",
            *scene_links_for_artifact(artifact, paths),
        ],
    )


def build_entity_page(entity: CanonEntity, scenes: list[SceneContract], paths: WikiPaths) -> str:
    referenced_by = [
        scene
        for scene in scenes
        if entity.name and entity.name.lower() in searchable_scene_text(scene)
    ]
    return page(
        entity.name,
        "canon_entity",
        ["canon", entity.entity_type],
        [
            f"# {entity.name}",
            "",
            f"Project: {paths.link('project.md', paths.project.title)}",
            "",
            "## Canon Type",
            entity.entity_type,
            "",
            "## Summary",
            entity.summary or "_No summary recorded._",
            "",
            "## Current State",
            entity.current_state or "_No current state recorded._",
            "",
            "## Constraints",
            entity.constraints or "_No constraints recorded._",
            "",
            "## Last Seen",
            entity.last_seen or "_No last-seen marker recorded._",
            "",
            "## Timeline Notes",
            entity.timeline_notes or "_No timeline notes recorded._",
            "",
            "## Referenced By Scenes",
            *scene_links(referenced_by, paths),
        ],
    )


def build_memory_page(record: MemoryRecord, paths: WikiPaths) -> str:
    source_links = source_ref_links(record.source_ref, paths)
    return page(
        record.title,
        "memory_record",
        ["memory", record.record_type],
        [
            f"# {record.title}",
            "",
            f"Project: {paths.link('project.md', paths.project.title)}",
            "",
            "## Type",
            record.record_type,
            "",
            "## Scope",
            record.scope or "_No scope recorded._",
            "",
            "## Source",
            record.source_ref or "_No source reference recorded._",
            "",
            "## Source Links",
            *(source_links or ["- _No matching exported source page found._"]),
            "",
            "## Content",
            record.content,
            "",
            "## Tags",
            record.tags or "_No tags recorded._",
        ],
    )


def build_scene_page(
    scene: SceneContract,
    canon_entities: list[CanonEntity],
    memory_records: list[MemoryRecord],
    paths: WikiPaths,
) -> str:
    linked_entities = [
        entity
        for entity in canon_entities
        if entity.name and entity.name.lower() in searchable_scene_text(scene)
    ]
    linked_memory = [record for record in memory_records if record_matches_scene(record, scene)]
    manuscript_path = paths.manuscript_scene_path(scene.id)
    manuscript_link = (
        paths.link(manuscript_path, "Accepted manuscript scene") if manuscript_path else ""
    )
    return page(
        f"{scene.sequence}. {scene.title}",
        "scene",
        ["scene", "contract"],
        [
            f"# {scene.sequence}. {scene.title}",
            "",
            f"Project: {paths.link('project.md', paths.project.title)}",
            f"Source artifact: {artifact_link(scene.source_artifact_step, paths)}",
            f"Accepted manuscript: {manuscript_link or '_Not accepted yet._'}",
            "",
            "## Contract",
            f"- POV: {scene.pov or 'unset'}",
            f"- Goal: {scene.goal or 'unset'}",
            f"- Conflict: {scene.conflict or 'unset'}",
            f"- Turning point: {scene.turning_point or 'unset'}",
            "",
            "## Required Canon",
            scene.required_canon or "_No required Canon recorded._",
            "",
            "## Forbidden Facts",
            scene.forbidden_facts or "_No forbidden facts recorded._",
            "",
            "## Open Threads",
            scene.open_threads or "_No open threads recorded._",
            "",
            "## Linked Canon Entities",
            *entity_links(linked_entities, paths),
            "",
            "## Linked Memory / Style",
            *memory_links(linked_memory, paths),
        ],
    )


def build_manuscript_page(scene: ManuscriptScene, paths: WikiPaths) -> str:
    source_scene = next(
        (candidate for candidate in paths.scenes if candidate.id == scene.scene_id), None
    )
    source_link = (
        paths.link(paths.scene_path(source_scene), f"{source_scene.sequence}. {source_scene.title}")
        if source_scene
        else "_Source Scene Contract not found._"
    )
    return page(
        scene.title,
        "manuscript_scene",
        ["manuscript", "accepted"],
        [
            f"# {scene.title}",
            "",
            f"Project: {paths.link('project.md', paths.project.title)}",
            f"Scene Contract: {source_link}",
            f"Version: {scene.version}",
            f"Accepted at: {scene.accepted_at}",
            "",
            "## Content",
            scene.content,
        ],
    )


def build_graph_page(
    project: ProjectSummary,
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
) -> str:
    nodes = build_graph_nodes(
        project.id, project.title, artifacts, canon_entities, scenes, memory_records
    )
    edges = build_graph_edges(project.id, artifacts, canon_entities, scenes, memory_records)
    risks = build_graph_risks(artifacts, canon_entities, scenes, memory_records)
    lines = [
        "# Graph / Structure",
        "",
        "## Summary",
        f"- Nodes: {len(nodes)}",
        f"- Edges: {len(edges)}",
        f"- Risks: {len(risks)}",
        f"- Unresolved threads: {sum(1 for scene in scenes if scene.open_threads)}",
        "",
        "## Risks",
    ]
    lines.extend(
        f"- **{risk.severity.upper()}** `{risk.source_id or 'project'}`: {risk.title} - {risk.detail}"
        for risk in risks
    )
    if not risks:
        lines.append("- _No structure risks found._")
    lines.extend(["", "## Edges"])
    lines.extend(
        f"- `{edge.source}` {edge.edge_type} `{edge.target}` ({edge.label or 'unlabeled'})"
        for edge in edges
    )
    if not edges:
        lines.append("- _No graph edges found._")
    return page("Graph / Structure", "graph", ["graph", "structure"], lines)


def build_state_snapshot(
    project: ProjectSummary,
    artifacts: list[SnowflakeArtifact],
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
    memory_records: list[MemoryRecord],
    manuscript_scenes: list[ManuscriptScene],
    generated_at: str,
) -> str:
    payload = {
        "generated_at": generated_at,
        "project": project.model_dump(),
        "snowflake_artifacts": [artifact.model_dump() for artifact in artifacts],
        "canon_entities": [entity.model_dump() for entity in canon_entities],
        "scene_contracts": [scene.model_dump() for scene in scenes],
        "memory_records": [record.model_dump() for record in memory_records],
        "manuscript_scenes": [scene.model_dump() for scene in manuscript_scenes],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def page(title: str, page_type: str, tags: list[str], body: list[str]) -> str:
    safe_tags = ", ".join(json.dumps(tag) for tag in tags if tag)
    frontmatter = [
        "---",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"type: {page_type}",
        f"tags: [{safe_tags}]",
        "sources: [raw/project-state.json]",
        "---",
        "",
    ]
    return "\n".join([*frontmatter, *body])


def scene_links_for_artifact(artifact: SnowflakeArtifact, paths: WikiPaths) -> list[str]:
    linked = [scene for scene in paths.scenes if scene.source_artifact_step == artifact.step_number]
    return scene_links(linked, paths)


def scene_links(scenes: list[SceneContract], paths: WikiPaths) -> list[str]:
    if not scenes:
        return ["- _No scene references found._"]
    return [
        f"- {paths.link(paths.scene_path(scene), f'{scene.sequence}. {scene.title}')}"
        for scene in scenes
    ]


def entity_links(entities: list[CanonEntity], paths: WikiPaths) -> list[str]:
    if not entities:
        return ["- _No Canon entity links found._"]
    return [f"- {paths.link(paths.entity_path(entity), entity.name)}" for entity in entities]


def memory_links(records: list[MemoryRecord], paths: WikiPaths) -> list[str]:
    if not records:
        return ["- _No Memory / Style links found._"]
    return [f"- {paths.link(paths.memory_path(record), record.title)}" for record in records]


def artifact_link(step_number: int, paths: WikiPaths) -> str:
    artifact = next(
        (candidate for candidate in paths.artifacts if candidate.step_number == step_number),
        None,
    )
    if artifact is None:
        return f"_Missing Snowflake step {step_number}_"
    return paths.link(
        paths.artifact_path(artifact), f"Step {artifact.step_number}: {artifact.artifact}"
    )


def source_ref_links(source_ref: str, paths: WikiPaths) -> list[str]:
    normalized = source_ref.strip().lower()
    if not normalized:
        return []
    links: list[str] = []
    for scene in paths.scenes:
        if normalized in scene.id.lower() or normalized in scene.title.lower():
            links.append(
                f"- {paths.link(paths.scene_path(scene), f'{scene.sequence}. {scene.title}')}"
            )
    for artifact in paths.artifacts:
        if normalized in {artifact.artifact.lower(), f"step {artifact.step_number}"}:
            links.append(
                f"- {paths.link(paths.artifact_path(artifact), f'Step {artifact.step_number}')}"
            )
    return links


def record_matches_scene(record: MemoryRecord, scene: SceneContract) -> bool:
    haystack = searchable_scene_text(scene)
    for value in (record.scope, record.source_ref, record.tags):
        normalized = value.strip().lower()
        if normalized and (normalized in haystack or scene.id.lower() in normalized):
            return True
    return False


def searchable_scene_text(scene: SceneContract) -> str:
    return " ".join(
        [
            scene.id,
            scene.title,
            scene.pov,
            scene.goal,
            scene.conflict,
            scene.turning_point,
            scene.required_canon,
            scene.forbidden_facts,
            scene.open_threads,
        ]
    ).lower()


def escape_link_label(label: str) -> str:
    return label.replace("|", "-")
