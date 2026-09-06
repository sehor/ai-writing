import type { ActiveSection } from '../types'

export const sections: {
  id: ActiveSection
  label: string
  description: string
  icon: string
}[] = [
  {
    id: 'snowflake',
    label: '雪花规划',
    description: '从一个念头，长成完整故事',
    icon: 'snowflake',
  },
  {
    id: 'canon',
    label: '故事设定',
    description: '让每个世界细节有据可循',
    icon: 'book',
  },
  {
    id: 'memory',
    label: '记忆与文风',
    description: '留住故事的声音与延续',
    icon: 'feather',
  },
  {
    id: 'graph',
    label: '结构分析',
    description: '发现故事中的联系与缺口',
    icon: 'graph',
  },
  {
    id: 'manuscript',
    label: '正文写作',
    description: '把故事写下去',
    icon: 'edit',
  },
]

export function readPreference<T>(key: string, fallback: T): T {
  try {
    return (
      JSON.parse(localStorage.getItem(`ai-writing:ui:v1:${key}`) ?? 'null') ??
      fallback
    )
  } catch {
    return fallback
  }
}
export function writePreference(key: string, value: unknown) {
  try {
    localStorage.setItem(`ai-writing:ui:v1:${key}`, JSON.stringify(value))
  } catch {
    /* UI preferences are optional. */
  }
}
export type WorkspaceLocation = {
  section: ActiveSection
  chapter: string
  scene: string
}
export function readLocation(projectId: string): WorkspaceLocation | null {
  const value = readPreference<WorkspaceLocation | null>(
    `location:${projectId}`,
    null,
  )
  return value &&
    sections.some((section) => section.id === value.section) &&
    typeof value.chapter === 'string' &&
    typeof value.scene === 'string'
    ? value
    : null
}
