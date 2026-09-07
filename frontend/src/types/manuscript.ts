export type ManuscriptChapter = {
  id: string
  project_id: string
  sequence: number
  title: string
  summary: string
}

export type ManuscriptChapterDraft = Omit<ManuscriptChapter, 'id' | 'project_id'>

export type ChapterCompileResponse = {
  project_id: string
  scene_id: string
  context: string
  draft: string
  checklist: string[]
}

export type ManuscriptProposalStatus = 'pending_review' | 'accepted' | 'rejected' | 'superseded'

export type ManuscriptGenerationReview = {
  schema_version: 1
  availability: 'structured' | 'legacy_prose_only'
  generation_run_id: string
  provider: string
  model: string
  material: {
    scene_id: string
    manuscript_prose: string
    entry_state_observed: string[]
    exit_state_produced: string[]
    scene_contract_coverage: {
      goal: string; conflict: string; turning_point: string; outcome: string; missing_elements: string[]
    }
    new_fact_candidates: { claim: string; entity_refs: string[]; reason_introduced: string; status: 'proposal' }[]
    design_deviation_proposals: {
      target_artifact_ref: string; current_design: string; proposed_change: string; reason: string; downstream_impact: string[]
    }[]
    continuity_questions: string[]
    source_refs: string[]
  } | null
}

export type ManuscriptProposal = {
  id: string
  project_id: string
  scene_id: string
  source: 'scene_contract' | 'legacy_snowflake_import'
  title: string
  content: string
  context: string
  checklist: string[]
  status: ManuscriptProposalStatus
  generation_review?: ManuscriptGenerationReview | null
  created_at: string
  reviewed_at: string
}

export type ManuscriptScene = {
  id: string
  project_id: string
  scene_id: string
  proposal_id: string
  title: string
  content: string
  version: number
  accepted_at: string
}

export type ManuscriptRevision = {
  id: string
  project_id: string
  scene_id: string
  proposal_id: string
  title: string
  content: string
  version: number
  created_at: string
}

export type ManuscriptRevisionDiff = {
  project_id: string
  left_revision_id: string
  right_revision_id: string
  left_title: string
  right_title: string
  diff_lines: string[]
}

export type ManuscriptExport = {
  project_id: string
  title: string
  scene_count: number
  content: string
  generated_at: string
}
