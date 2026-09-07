from app.models import ManuscriptChapter, ManuscriptScene, SceneContract
from app.domain_models.volume import ManuscriptVolume


def _build_volume_export(
    title: str,
    chapters: list[ManuscriptChapter],
    scene_pairs: list[tuple[ManuscriptScene, SceneContract | None]],
    volumes: list[ManuscriptVolume],
) -> str:
    sections = [f"# {title}", ""]
    chapter_ids = {chapter.id for chapter in chapters}
    assigned = {chapter_id for volume in volumes for chapter_id in volume.chapter_ids}
    groups = [
        (f"Volume {volume.sequence}: {volume.title}", set(volume.chapter_ids))
        for volume in sorted(volumes, key=lambda volume: (volume.sequence, volume.id))
    ]
    if chapter_ids - assigned:
        groups.append(("Unassigned Chapters", chapter_ids - assigned))
    for heading, group_ids in groups:
        sections.extend([f"## {heading}", ""])
        has_prose = False
        for chapter in sorted(chapters, key=lambda chapter: (chapter.sequence, chapter.id)):
            if chapter.id not in group_ids:
                continue
            sections.extend([f"### Chapter {chapter.sequence}: {chapter.title}", ""])
            for scene, contract in scene_pairs:
                if contract and contract.chapter_id == chapter.id:
                    sections.extend([f"#### {scene.title}", "", scene.content.strip(), ""])
                    has_prose = True
        if not has_prose:
            sections.extend(["_No accepted manuscript scenes in this group yet._", ""])
    orphan_scenes = [
        scene
        for scene, contract in scene_pairs
        if not contract or contract.chapter_id not in chapter_ids
    ]
    if orphan_scenes:
        sections.extend(["## Unassigned Scenes", ""])
        for scene in orphan_scenes:
            sections.extend([f"### {scene.title}", "", scene.content.strip(), ""])
    return "\n".join(sections).strip()


def build_export_markdown(
    title: str,
    chapters: list[ManuscriptChapter],
    scene_pairs: list[tuple[ManuscriptScene, SceneContract | None]],
    volumes: list[ManuscriptVolume] | None = None,
) -> str:
    if volumes:
        return _build_volume_export(title, chapters, scene_pairs, volumes)
    sections = [f"# {title}", ""]
    if not scene_pairs:
        sections.append("_No accepted manuscript scenes yet._")
        return "\n".join(sections).strip()

    chapter_by_id = {chapter.id: chapter for chapter in chapters}
    chapter_ids_with_scenes = {
        scene_contract.chapter_id
        for _, scene_contract in scene_pairs
        if scene_contract and scene_contract.chapter_id
    }
    if chapter_ids_with_scenes:
        for chapter in chapters:
            chapter_scenes = [
                scene
                for scene, scene_contract in scene_pairs
                if scene_contract and scene_contract.chapter_id == chapter.id
            ]
            if not chapter_scenes:
                continue
            sections.extend([f"## Chapter {chapter.sequence}: {chapter.title}", ""])
            for scene in chapter_scenes:
                sections.extend([f"### {scene.title}", "", scene.content.strip(), ""])

        orphan_scenes = [
            scene
            for scene, scene_contract in scene_pairs
            if not scene_contract
            or not scene_contract.chapter_id
            or scene_contract.chapter_id not in chapter_by_id
        ]
        if orphan_scenes:
            sections.extend(["## Unassigned Scenes", ""])
            for scene in orphan_scenes:
                sections.extend([f"### {scene.title}", "", scene.content.strip(), ""])
        return "\n".join(sections).strip()

    for scene, _ in scene_pairs:
        sections.extend([f"## {scene.title}", "", scene.content.strip(), ""])
    return "\n".join(sections).strip()
