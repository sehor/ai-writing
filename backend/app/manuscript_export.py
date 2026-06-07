from app.models import ManuscriptChapter, ManuscriptScene, SceneContract


def build_export_markdown(
    title: str,
    chapters: list[ManuscriptChapter],
    scene_pairs: list[tuple[ManuscriptScene, SceneContract | None]],
) -> str:
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
