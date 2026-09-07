import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ReferenceWorkspace from '../src/components/manuscript/ReferenceWorkspace.vue'
import { loadDraft } from '../src/services/draftCache'
import { useCopilotContextStore } from '../src/stores/copilotContext'
import { useEditorSessionStore } from '../src/stores/editorSession'
import { useManuscriptStore } from '../src/stores/manuscript'
import { useProjectContextStore } from '../src/stores/projectContext'
import { useProposalDraftStore } from '../src/stores/proposalDraft'
import { useReferenceApplicationStore } from '../src/stores/referenceApplication'
import { useReviewsStore } from '../src/stores/reviews'
import type { ManuscriptProposal, ManuscriptScene, ReferenceEditorContext, ReferenceSuggestion } from '../src/types'

const projectId = 'project-1'
const sceneId = 'scene-1'
const original = 'Before OLD After'
const proposal = {
  id: 'proposal-1',
  project_id: projectId,
  scene_id: sceneId,
  title: 'Draft',
  content: original,
  status: 'pending_review',
} as ManuscriptProposal

function context(sourceKind: 'proposal_draft' | 'accepted_manuscript', version = 2): ReferenceEditorContext {
  return {
    project_id: projectId,
    scene_id: sceneId,
    source_kind: sourceKind,
    proposal_id: sourceKind === 'proposal_draft' ? proposal.id : '',
    expected_scene_version: version,
    session_id: 'editor-session',
    snapshot_text: original,
    selection_mode: 'selection',
    selection_start: 7,
    selection_end: 10,
    selected_text: 'OLD',
  }
}

function suggestion(editorContext: ReferenceEditorContext): ReferenceSuggestion {
  return {
    id: 'suggestion-1',
    project_id: projectId,
    suggestion_type: 'prose_reference',
    scope_type: 'scene',
    scope_ref: sceneId,
    title: 'Reference',
    content: 'Candidate prose',
    rationale: '',
    used_context: '',
    canon_warnings: [],
    style_notes: [],
    graph_warnings: [],
    proposed_writebacks: [],
    workflow_trace: [],
    status: 'pending_review',
    created_at: '',
    reviewed_at: '',
    editor_context: editorContext,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  vi.useFakeTimers()
  vi.restoreAllMocks()
  useProjectContextStore().activeProjectId = projectId
})

afterEach(() => {
  useProposalDraftStore().reset()
  vi.useRealTimers()
})

test('previews and replaces a proposal selection through the existing dirty draft, blocks duplicate apply, and can undo', async () => {
  const draft = useProposalDraftStore()
  draft.open(projectId, proposal, 2)
  const editorContext = context('proposal_draft')
  useCopilotContextStore().register({
    project_id: projectId,
    scene_id: sceneId,
    source_kind: 'proposal_draft',
    proposal_id: proposal.id,
    expected_scene_version: 2,
    session_id: editorContext.session_id,
    snapshot_text: original,
  })
  const application = useReferenceApplicationStore()
  const reference = suggestion(editorContext)
  application.applicationText = 'NEW'
  application.mode = 'replace'

  expect(application.previewSuggestion(reference)).toBe(true)
  expect(application.previewText).toBe('Before NEW After')
  expect(draft.content).toBe(original)
  expect(draft.dirty).toBe(false)

  const fetch = vi.spyOn(globalThis, 'fetch')
  expect(application.applySuggestion(reference)).toBe(true)
  expect(draft.content).toBe('Before NEW After')
  expect(draft.dirty).toBe(true)
  expect(fetch).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(400)
  expect(loadDraft(draft.scopeKey)?.value).toMatchObject({ content: 'Before NEW After', expected_scene_version: 2 })

  expect(application.applySuggestion(reference)).toBe(false)
  expect(draft.content).toBe('Before NEW After')
  expect(application.error).toContain('重新选择')

  expect(application.undo()).toBe(true)
  expect(draft.content).toBe(original)
  expect(draft.dirty).toBe(false)
})

test('inserts after the selected accepted-manuscript text and refuses undo after later author edits', () => {
  const manuscript = useManuscriptStore()
  const scene = {
    id: 'manuscript-1',
    project_id: projectId,
    scene_id: sceneId,
    title: 'Accepted',
    content: original,
    version: 3,
  } as ManuscriptScene
  manuscript.manuscriptScenes = [scene]
  manuscript.startEditingManuscriptScene(scene)
  const editorContext = context('accepted_manuscript', 3)
  useCopilotContextStore().register({
    project_id: projectId,
    scene_id: sceneId,
    source_kind: 'accepted_manuscript',
    proposal_id: '',
    expected_scene_version: 3,
    session_id: editorContext.session_id,
    snapshot_text: original,
  })
  const application = useReferenceApplicationStore()
  const reference = suggestion(editorContext)
  application.applicationText = 'NEW'
  application.mode = 'insert'

  expect(application.applySuggestion(reference)).toBe(true)
  expect(manuscript.manuscriptEditContent).toBe('Before OLDNEW After')
  expect(useEditorSessionStore().isDirty(manuscript.manuscriptEditScopeKey())).toBe(true)

  manuscript.manuscriptEditContent += ' author edit'
  expect(application.undo()).toBe(false)
  expect(manuscript.manuscriptEditContent).toBe('Before OLDNEW After author edit')
  expect(application.error).toContain('继续修改')
})

test('reference UI separates review status from preview/apply/undo and requires explicit application text', async () => {
  const draft = useProposalDraftStore()
  draft.open(projectId, proposal, 2)
  const editorContext = context('proposal_draft')
  useCopilotContextStore().register({
    project_id: projectId,
    scene_id: sceneId,
    source_kind: 'proposal_draft',
    proposal_id: proposal.id,
    expected_scene_version: 2,
    session_id: editorContext.session_id,
    snapshot_text: original,
  })
  const reference = suggestion(editorContext)
  const reviews = useReviewsStore()
  reviews.referenceSuggestions = [reference]
  reviews.activeReferenceId = reference.id
  const wrapper = mount(ReferenceWorkspace)

  expect(wrapper.text()).toContain('采纳状态只记录评审')
  expect(wrapper.text()).toContain('接受参考建议')
  expect(wrapper.get('[aria-label="待应用文本"]').element).toHaveProperty('value', '')
  expect(wrapper.get('button[data-testid="apply-reference"]').attributes('disabled')).toBeDefined()

  await wrapper.get('[aria-label="待应用文本"]').setValue('NEW')
  await wrapper.get('button[data-testid="preview-reference"]').trigger('click')
  expect(wrapper.get('[aria-label="应用预览"]').text()).toContain('Before NEW After')
  expect(draft.content).toBe(original)

  const fetch = vi.spyOn(globalThis, 'fetch')
  await wrapper.get('button[data-testid="apply-reference"]').trigger('click')
  expect(draft.content).toBe('Before NEW After')
  expect(reviews.activeReferenceSuggestion?.status).toBe('pending_review')
  expect(fetch).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('尚未保存正式版本')

  await wrapper.get('button[data-testid="undo-reference"]').trigger('click')
  expect(draft.content).toBe(original)
  wrapper.unmount()
})

test('rejects stale target version, session, or original selection instead of overwriting newer text', () => {
  const draft = useProposalDraftStore()
  draft.open(projectId, proposal, 2)
  const editorContext = context('proposal_draft')
  const copilot = useCopilotContextStore()
  copilot.register({
    project_id: projectId,
    scene_id: sceneId,
    source_kind: 'proposal_draft',
    proposal_id: proposal.id,
    expected_scene_version: 2,
    session_id: 'different-session',
    snapshot_text: original,
  })
  const application = useReferenceApplicationStore()
  application.applicationText = 'NEW'
  expect(application.applySuggestion(suggestion(editorContext))).toBe(false)
  expect(draft.content).toBe(original)

  copilot.register({
    project_id: projectId,
    scene_id: sceneId,
    source_kind: 'proposal_draft',
    proposal_id: proposal.id,
    expected_scene_version: 3,
    session_id: editorContext.session_id,
    snapshot_text: original,
  })
  draft.rebase(3)
  expect(application.applySuggestion(suggestion(editorContext))).toBe(false)
  expect(draft.content).toBe(original)

  const changed = context('proposal_draft', 3)
  changed.selected_text = 'WRONG'
  expect(application.applySuggestion(suggestion(changed))).toBe(false)
  expect(draft.content).toBe(original)
})
