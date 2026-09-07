export type CanonEntityType = 'character' | 'location' | 'item' | 'faction' | 'rule'

export type CanonEntity = {
  id: string
  project_id: string
  entity_type: CanonEntityType
  name: string
  summary: string
  current_state: string
  constraints: string
  last_seen: string
  timeline_notes: string
  version: number
  updated_at: string
}

export type CanonDraft = Omit<
  CanonEntity,
  'id' | 'project_id' | 'version' | 'updated_at'
>
