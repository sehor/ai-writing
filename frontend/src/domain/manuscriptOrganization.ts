import type { ManuscriptChapter, SceneContract } from '../types'
import type { ManuscriptVolume } from '../types/volume'

export function organizeManuscript(volumes: ManuscriptVolume[], chapters: ManuscriptChapter[], scenes: SceneContract[], query = '') {
  const orderedChapters = [...chapters].sort((a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id))
  const assigned = new Set(volumes.flatMap(v => v.chapter_ids))
  const chapterIds = new Set(chapters.map(c => c.id))
  const scenesByChapter = new Map<string, SceneContract[]>()
  for (const scene of scenes) {
    const key = chapterIds.has(scene.chapter_id) ? scene.chapter_id : ''
    const group = scenesByChapter.get(key) ?? []
    group.push(scene); scenesByChapter.set(key, group)
  }
  const sections = [
    ...[...volumes].sort((a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id)).map(volume => ({
      id: volume.id, title: `${volume.sequence} · ${volume.title}`, chapters: orderedChapters.filter(c => volume.chapter_ids.includes(c.id)),
    })),
    { id: '', title: '未分卷', chapters: orderedChapters.filter(c => !assigned.has(c.id)) },
  ]
  const needle = query.trim().toLowerCase()
  return sections.map(section => {
    const groups = section.chapters.map(chapter => ({ id: chapter.id, title: chapter.title,
      scenes: scenesByChapter.get(chapter.id) ?? [],
    }))
    if (!section.id) groups.push({ id: '', title: '未分章场景', scenes: scenesByChapter.get('') ?? [] })
    return { id: section.id, title: section.title, groups: groups.map(group => ({ ...group,
      scenes: [...group.scenes].filter(scene => `${section.title} ${group.title} ${scene.title}`.toLowerCase().includes(needle))
        .sort((a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id)),
    })).filter(group => group.scenes.length || (!!group.id && `${section.title} ${group.title}`.toLowerCase().includes(needle))) }
  }).filter(section => section.groups.length || (!!section.id && section.title.toLowerCase().includes(needle)))
}
