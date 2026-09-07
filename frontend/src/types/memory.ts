export type MemoryRecordType = 'chapter_summary' | 'prose_sample' | 'voice_sample' | 'style_rule'

export type MemoryRecord = {
  id: string
  project_id: string
  record_type: MemoryRecordType
  title: string
  scope: string
  content: string
  tags: string
  source_ref: string
}

export type MemoryDraft = Omit<MemoryRecord, 'id' | 'project_id'>
