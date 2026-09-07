export type SceneContract = {
  id: string
  project_id: string
  plan_version?: number
  manuscript_plan_version?: number
  source_record_step?: 0 | 8
  source_record_id?: string
  source_record_revision_id?: string
  chapter_id: string
  sequence: number
  title: string
  pov: string
  goal: string
  conflict: string
  turning_point: string
  outcome: string
  required_canon: string
  forbidden_facts: string
  information_delta: string
  character_state_delta: string
  story_thread_actions: string
  open_threads: string
  source_artifact_step: number
}

export type SceneDraft = Omit<SceneContract, 'id' | 'project_id' | 'plan_version' | 'manuscript_plan_version' | 'source_record_step' | 'source_record_id' | 'source_record_revision_id'>
