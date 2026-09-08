import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useEditorSessionStore } from './editorSession'
import { clearDraft } from '../services/draftCache'
import { cancelAutosave, isScopeDirty, persistDraft, queueAutosave, restoreCachedDraft, setBaseline } from '../services/draftSessions'
import type { ManuscriptProposal } from '../types'

export type ProposalDraftValue = { title: string; content: string; expected_scene_version: number }

export const useProposalDraftStore = defineStore('proposalDraft', () => {
  const projectId = ref('')
  const proposalId = ref('')
  const title = ref('')
  const content = ref('')
  const expectedSceneVersion = ref(0)
  const restored = ref(false)
  const visible = ref(false)
  const submitting = ref(false)
  const leavePending = ref(false)
  const leaveError = ref('')
  let pendingAction: (() => void) | undefined
  let initial: ProposalDraftValue = { title: '', content: '', expected_scene_version: 0 }
  let epoch = 0
  const approved = ref('')
  const session = useEditorSessionStore()
  const scopeKey = computed(() => `proposal:${projectId.value}:${proposalId.value}`)
  const dirty = computed(() => session.isDirty(scopeKey.value))
  let hydrating = false
  const snapshot = (): ProposalDraftValue => ({ title: title.value, content: content.value, expected_scene_version: expectedSceneVersion.value })
  const fingerprint = () => `${scopeKey.value}:${JSON.stringify(snapshot())}`
  const leaveApproved = computed(() => approved.value === fingerprint())
  function capture() { return { epoch, key: scopeKey.value, value: snapshot() } }
  function matches(request: ReturnType<typeof capture>) { return request.epoch === epoch && request.key === scopeKey.value }

  function canLeave(action: () => void): boolean {
    if (submitting.value) { leaveError.value = '正在接受，请稍候。'; return false }
    if (!visible.value || !dirty.value || leaveApproved.value) return true
    if (!leavePending.value) { pendingAction = action; leavePending.value = true; leaveError.value = '' }
    return false
  }
  function navigate(action: () => void) { if (canLeave(action)) action() }
  function resolveLeave(choice: 'save' | 'discard' | 'cancel') {
    if (choice === 'cancel') { pendingAction = undefined; leavePending.value = false; return }
    if (submitting.value) return
    if (choice === 'save') {
      if (!persistDraft(scopeKey.value, snapshot())) { leaveError.value = '草稿保存失败，请重试或取消离开。'; return }
    } else {
      cancelAutosave(scopeKey.value)
      if (!clearDraft(scopeKey.value)) { leaveError.value = '草稿缓存清理失败，请重试或取消离开。'; return }
      hydrating = true
      title.value = initial.title; content.value = initial.content; expectedSceneVersion.value = initial.expected_scene_version
      setBaseline(scopeKey.value, initial)
      hydrating = false
    }
    approved.value = fingerprint()
    const action = pendingAction
    pendingAction = undefined; leavePending.value = false; leaveError.value = ''
    action?.()
  }

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
    epoch++; approved.value = ''
    initial = { title: proposal.title, content: proposal.content, expected_scene_version: sceneVersion }
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

  function committed(request = capture()) {
    if (!matches(request) || JSON.stringify(request.value) !== JSON.stringify(snapshot())) return false
    clearDraft(scopeKey.value)
    setBaseline(scopeKey.value, snapshot())
    restored.value = false
    return true
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
    epoch++; approved.value = ''; visible.value = false
    pendingAction = undefined; leavePending.value = false
    projectId.value = ''; proposalId.value = ''; title.value = ''; content.value = ''
    restored.value = false; expectedSceneVersion.value = 0
    hydrating = false
  }

  return { projectId, proposalId, title, content, expectedSceneVersion, restored, scopeKey, dirty, snapshot, open, persist, committed, rebase, reset,
    visible, submitting, leavePending, leaveError, leaveApproved, capture, matches, canLeave, navigate, resolveLeave }
})
