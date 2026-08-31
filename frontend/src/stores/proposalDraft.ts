import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useEditorSessionStore } from './editorSession'
import { clearDraft } from '../services/draftCache'
import { isScopeDirty, persistDraft, queueAutosave, restoreCachedDraft, setBaseline } from '../services/draftSessions'
import type { ManuscriptProposal } from '../types'

export type ProposalDraftValue = { title: string; content: string; expected_scene_version: number }

export const useProposalDraftStore = defineStore('proposalDraft', () => {
  const projectId = ref('')
  const proposalId = ref('')
  const title = ref('')
  const content = ref('')
  const expectedSceneVersion = ref(0)
  const restored = ref(false)
  const session = useEditorSessionStore()
  const scopeKey = computed(() => `proposal:${projectId.value}:${proposalId.value}`)
  const dirty = computed(() => session.isDirty(scopeKey.value))
  let hydrating = false
  const snapshot = (): ProposalDraftValue => ({ title: title.value, content: content.value, expected_scene_version: expectedSceneVersion.value })

  watch([title, content, expectedSceneVersion], () => {
    if (hydrating || !projectId.value || !proposalId.value) return
    const key = scopeKey.value
    const value = snapshot()
    if (isScopeDirty(key, value)) session.markDirty(key)
    else { session.markClean(key); clearDraft(key) }
    // Capture this scope's value; delayed saves cannot read a different draft.
    queueAutosave(key, () => value)
  }, { flush: 'sync' })

  function persist() {
    if (projectId.value && proposalId.value && dirty.value) persistDraft(scopeKey.value, snapshot())
  }

  function open(id: string, proposal: ManuscriptProposal, sceneVersion: number) {
    if (projectId.value === id && proposalId.value === proposal.id) return
    persist()
    hydrating = true
    projectId.value = id; proposalId.value = proposal.id
    const initial = { title: proposal.title, content: proposal.content, expected_scene_version: sceneVersion }
    setBaseline(scopeKey.value, initial)
    const cached = restoreCachedDraft<ProposalDraftValue>(scopeKey.value)?.value
    const validCache = cached && typeof cached.title === 'string' && typeof cached.content === 'string' &&
      Number.isInteger(cached.expected_scene_version) && cached.expected_scene_version >= 0
    const value = validCache ? cached : initial
    title.value = value.title; content.value = value.content; expectedSceneVersion.value = value.expected_scene_version
    restored.value = !!validCache
    if (isScopeDirty(scopeKey.value, snapshot())) session.markDirty(scopeKey.value)
    hydrating = false
  }

  function committed() {
    clearDraft(scopeKey.value)
    setBaseline(scopeKey.value, snapshot())
    restored.value = false
  }

  /** Called only after the author explicitly reviews the newer official text. */
  function rebase(sceneVersion: number) {
    expectedSceneVersion.value = sceneVersion
    persist()
  }

  function reset() {
    persist()
    session.dropEditor(scopeKey.value)
    hydrating = true
    projectId.value = ''; proposalId.value = ''; title.value = ''; content.value = ''
    restored.value = false; expectedSceneVersion.value = 0
    hydrating = false
  }

  return { projectId, proposalId, title, content, expectedSceneVersion, restored, scopeKey, dirty, snapshot, open, persist, committed, rebase, reset }
})
