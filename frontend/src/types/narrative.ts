export type StoryThreadStatus = 'planned' | 'planted' | 'developing' | 'dormant' | 'paid_off' | 'abandoned'

export type StoryThread = {
  id: string; project_id: string; title: string; thread_type: string
  status: StoryThreadStatus; importance: number; planted_at: number | null
  target_payoff_from: number | null; target_payoff_to: number | null; reveal_constraints: string
}

export type NarrativeRelation = {
  id: string; project_id: string; source: string; target: string; relation: string
  valid_from: number; valid_to: number | null; confidence: number; source_ref: string; status: string
}
export type StoryFactStatus = 'planned' | 'confirmed' | 'superseded' | 'retracted'
export type KnowledgeScope = 'world_truth' | 'reader_knowledge' | 'character_knowledge'

export type StoryFact = {
  id: string
  project_id: string
  subject: string
  predicate: string
  value: string
  valid_from_scene: number
  valid_to_scene: number | null
  reader_visible_from: number | null
  source_ref: string
  status: StoryFactStatus
  version: number
  updated_at: string
}

export type KnowledgeState = {
  id: string
  project_id: string
  fact_id: string
  scope: KnowledgeScope
  character: string
  known_from_scene: number
  source_ref: string
  status: StoryFactStatus
  version: number
  updated_at: string
}

export type NarrativeRevision = {
  id: string
  project_id: string
  fact_id: string
  knowledge_state_id: string
  version: number
  reason: string
  created_at: string
  record: StoryFact | KnowledgeState
}
