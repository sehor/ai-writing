import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { readErrorDetail } from '../api/errors'
import { confirmLeave } from '../composables/useDirtyGuard'
import {
  discardSavedScope,
  isScopeDirty,
  persistDraft,
  queueAutosave,
  restoreEntryDraft,
  setBaseline,
} from '../services/draftSessions'
import type {
  DirectorReport,
  KnowledgeScope,
  KnowledgeState,
  KnowledgeStateDraft,
  NarrativeRelation,
  NarrativeRevision,
  StoryFact,
  StoryFactDraft,
  StoryStateResponse,
  StoryThread,
} from '../types'
import { useProjectContextStore } from './projectContext'

/** Structural narrative state plus the author-owned temporal fact/knowledge editor. */
export const useNarrativeStore = defineStore('narrative', () => {
  const context = useProjectContextStore()

  // Existing structural surfaces.
  const threads = ref<StoryThread[]>([])
  const relations = ref<NarrativeRelation[]>([])
  const director = ref<DirectorReport | null>(null)
  const error = ref('')
  const isLoading = ref(false)

  // Author-visible temporal fact maintenance.
  const facts = ref<StoryFact[]>([])
  const activeFactId = ref('')
  const activeFact = computed(() => facts.value.find((item) => item.id === activeFactId.value))
  const factDraft = ref<StoryFactDraft>(createEmptyFactDraft())
  const factError = ref('')
  const factStatus = ref('')
  const isSavingFact = ref(false)
  const isRetractingFact = ref(false)
  const isLoadingFactDetails = ref(false)
  const knowledgeStates = ref<KnowledgeState[]>([])
  const history = ref<NarrativeRevision[]>([])

  // Knowledge-state maintenance for the selected fact.
  const activeKnowledgeId = ref('')
  const knowledgeDraft = ref<KnowledgeStateDraft>(createEmptyKnowledgeDraft())
  const knowledgeError = ref('')
  const knowledgeStatus = ref('')
  const isSavingKnowledge = ref(false)
  const isRetractingKnowledge = ref(false)

  // Scene-safe author preview. This is deliberately sourced only from /story-state.
  const storyState = ref<StoryStateResponse | null>(null)
  const previewError = ref('')
  const previewStatus = ref('')
  const isLoadingPreview = ref(false)

  let controller: AbortController | undefined
  let factDetailEpoch = 0
  let factSelectionEpoch = 0
  let knowledgeSelectionEpoch = 0
  let previewEpoch = 0
  let hydratingFact = false
  let hydratingKnowledge = false

  const activeKnowledge = computed(() => knowledgeStates.value.find((item) => item.id === activeKnowledgeId.value))
  const knowledgeReadOnly = computed(() => activeKnowledge.value?.scope === 'world_truth')

  function createEmptyFactDraft(): StoryFactDraft {
    return {
      subject: '', predicate: '', value: '', valid_from_scene: 0, valid_to_scene: null,
      reader_visible_from: null, source_ref: '', status: 'confirmed', reason: '',
    }
  }

  function createEmptyKnowledgeDraft(scope: Exclude<KnowledgeScope, 'world_truth'> = 'character_knowledge'): KnowledgeStateDraft {
    return {
      scope, character: '', known_from_scene: activeFact.value?.valid_from_scene ?? 0,
      source_ref: '', status: 'confirmed', reason: '',
    }
  }

  function factToDraft(item: StoryFact): StoryFactDraft {
    return {
      subject: item.subject, predicate: item.predicate, value: item.value,
      valid_from_scene: item.valid_from_scene, valid_to_scene: item.valid_to_scene,
      reader_visible_from: item.reader_visible_from, source_ref: item.source_ref,
      status: item.status, reason: '',
    }
  }

  function knowledgeToDraft(item: KnowledgeState): KnowledgeStateDraft {
    return {
      scope: item.scope, character: item.character, known_from_scene: item.known_from_scene,
      source_ref: item.source_ref, status: item.status, reason: '',
    }
  }

  function isActiveProject(projectId: string) {
    return projectId === context.activeProjectId
  }

  function factScopeKey(projectId = context.activeProjectId, factId = activeFactId.value) {
    return `narrativeFact:${projectId}:${factId || 'new'}`
  }

  function knowledgeScopeKey(
    projectId = context.activeProjectId,
    factId = activeFactId.value,
    knowledgeId = activeKnowledgeId.value,
  ) {
    return `narrativeKnowledge:${projectId}:${factId || 'none'}:${knowledgeId || 'new'}`
  }

  watch(factDraft, () => {
    if (hydratingFact) return
    queueAutosave(factScopeKey(), () => factDraft.value)
  }, { deep: true, flush: 'sync' })

  watch(knowledgeDraft, () => {
    if (hydratingKnowledge || !activeFactId.value) return
    queueAutosave(knowledgeScopeKey(), () => knowledgeDraft.value)
  }, { deep: true, flush: 'sync' })

  function hydrateFactDraft(item: StoryFact | undefined) {
    hydratingFact = true
    const baseline = item ? factToDraft(item) : createEmptyFactDraft()
    factDraft.value = baseline
    factStatus.value = ''
    factError.value = ''
    restoreEntryDraft<StoryFactDraft>(factScopeKey(), baseline, (cached) => {
      factDraft.value = { ...baseline, ...cached }
    }, (message) => { factStatus.value = message })
    hydratingFact = false
  }

  function hydrateKnowledgeDraft(item: KnowledgeState | undefined, scope?: Exclude<KnowledgeScope, 'world_truth'>) {
    hydratingKnowledge = true
    const baseline = item ? knowledgeToDraft(item) : createEmptyKnowledgeDraft(scope)
    knowledgeDraft.value = baseline
    knowledgeStatus.value = ''
    knowledgeError.value = ''
    setBaseline(knowledgeScopeKey(), baseline)
    if (!item || item.scope !== 'world_truth') {
      restoreEntryDraft<KnowledgeStateDraft>(knowledgeScopeKey(), baseline, (cached) => {
        knowledgeDraft.value = { ...baseline, ...cached }
      }, (message) => { knowledgeStatus.value = message })
    }
    hydratingKnowledge = false
  }

  function allowKnowledgeLeave() {
    if (!activeFactId.value) return true
    const scope = knowledgeScopeKey()
    if (!isScopeDirty(scope, knowledgeDraft.value)) return true
    if (!confirmLeave(scope, activeKnowledgeId.value ? '知识状态编辑' : '新建知识状态')) return false
    persistDraft(scope, knowledgeDraft.value)
    return true
  }

  function allowFactLeave() {
    if (!allowKnowledgeLeave()) return false
    const scope = factScopeKey()
    if (!isScopeDirty(scope, factDraft.value)) return true
    if (!confirmLeave(scope, activeFactId.value ? '时态事实编辑' : '新建时态事实')) return false
    persistDraft(scope, factDraft.value)
    return true
  }

  async function loadFactDetails(projectId: string, factId: string) {
    if (!projectId || !factId) {
      knowledgeStates.value = []
      history.value = []
      return
    }
    const epoch = ++factDetailEpoch
    isLoadingFactDetails.value = true
    try {
      const [knowledgeResponse, historyResponse] = await Promise.all([
        fetchApi(`/projects/${projectId}/story-facts/${factId}/knowledge-states`),
        fetchApi(`/projects/${projectId}/story-facts/${factId}/history`),
      ])
      if (!knowledgeResponse.ok || !historyResponse.ok) throw new Error('事实详情加载失败，请重试。')
      const [loadedKnowledge, loadedHistory] = await Promise.all([knowledgeResponse.json(), historyResponse.json()])
      if (epoch !== factDetailEpoch || !isActiveProject(projectId) || activeFactId.value !== factId) return
      knowledgeStates.value = loadedKnowledge
      history.value = loadedHistory
      if (activeKnowledgeId.value && !knowledgeStates.value.some((item) => item.id === activeKnowledgeId.value)) {
        activeKnowledgeId.value = ''
        hydrateKnowledgeDraft(undefined)
      }
    } catch (reason) {
      if (epoch === factDetailEpoch && isActiveProject(projectId) && activeFactId.value === factId) {
        factError.value = reason instanceof Error ? reason.message : '事实详情加载失败，请重试。'
      }
    } finally {
      if (epoch === factDetailEpoch) isLoadingFactDetails.value = false
    }
  }

  async function selectFact(factId: string) {
    if (factId === activeFactId.value && factId) {
      await loadFactDetails(context.activeProjectId, factId)
      return true
    }
    if (!allowFactLeave()) return false
    factSelectionEpoch += 1
    knowledgeSelectionEpoch += 1
    activeFactId.value = factId
    activeKnowledgeId.value = ''
    knowledgeStates.value = []
    history.value = []
    hydrateFactDraft(facts.value.find((item) => item.id === factId))
    hydrateKnowledgeDraft(undefined)
    if (factId) await loadFactDetails(context.activeProjectId, factId)
    return true
  }

  async function startNewFact() {
    return selectFact('')
  }

  function selectKnowledge(knowledgeId: string) {
    if (knowledgeId === activeKnowledgeId.value) return true
    if (!allowKnowledgeLeave()) return false
    knowledgeSelectionEpoch += 1
    activeKnowledgeId.value = knowledgeId
    hydrateKnowledgeDraft(knowledgeStates.value.find((item) => item.id === knowledgeId))
    return true
  }

  function startNewKnowledge(scope: Exclude<KnowledgeScope, 'world_truth'> = 'character_knowledge') {
    if (!allowKnowledgeLeave()) return false
    knowledgeSelectionEpoch += 1
    activeKnowledgeId.value = ''
    hydrateKnowledgeDraft(undefined, scope)
    return true
  }

  function validateFactDraft() {
    const draft = factDraft.value
    if (!draft.subject.trim() || !draft.predicate.trim() || !draft.value.trim()) return '请填写事实主体、关系和内容。'
    if (!Number.isInteger(draft.valid_from_scene) || draft.valid_from_scene < 0 || draft.valid_from_scene > 999) return '开始场景必须是 0–999 的整数。'
    if (draft.valid_to_scene !== null && (!Number.isInteger(draft.valid_to_scene) || draft.valid_to_scene < draft.valid_from_scene || draft.valid_to_scene > 999)) return '结束场景必须不早于开始场景，且不超过 999。'
    if (draft.reader_visible_from !== null && (!Number.isInteger(draft.reader_visible_from) || draft.reader_visible_from < draft.valid_from_scene || (draft.valid_to_scene !== null && draft.reader_visible_from > draft.valid_to_scene))) return '读者可见时点必须落在事实有效场景范围内。'
    if (activeFactId.value && !draft.reason.trim()) return '更正已有事实时请填写更正原因。'
    return ''
  }

  function cloneDraft<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T
  }

  function factPayload(draft: StoryFactDraft) {
    return {
      subject: draft.subject.trim(), predicate: draft.predicate.trim(), value: draft.value.trim(),
      valid_from_scene: draft.valid_from_scene, valid_to_scene: draft.valid_to_scene,
      reader_visible_from: draft.reader_visible_from, source_ref: draft.source_ref.trim(), status: draft.status,
    }
  }

  async function saveFact() {
    factError.value = ''
    factStatus.value = ''
    const projectId = context.activeProjectId
    if (!projectId) { factError.value = '请先创建或选择项目。'; return false }
    const validation = validateFactDraft()
    if (validation) { factError.value = validation; return false }
    if (isSavingFact.value) return false
    const recordId = activeFactId.value
    const current = activeFact.value
    if (recordId && !current) { factError.value = '当前事实已不存在，请刷新后重试。'; return false }
    const selection = factSelectionEpoch
    const requestScope = factScopeKey(projectId, recordId)
    const snapshot = cloneDraft(factDraft.value)
    const body = {
      ...factPayload(snapshot),
      ...(current ? { expected_version: current.version, reason: snapshot.reason.trim() } : {}),
    }
    isSavingFact.value = true
    try {
      const response = await fetchApi(recordId ? `/projects/${projectId}/story-facts/${recordId}` : `/projects/${projectId}/story-facts`, {
        method: recordId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        if (response.status === 409) throw new Error(detail.message || '事实版本已变化，请刷新后重新核对。')
        throw new Error(detail.message || '事实保存失败。')
      }
      const saved: StoryFact = await response.json()
      if (!isActiveProject(projectId) || selection !== factSelectionEpoch) return false
      facts.value = [saved, ...facts.value.filter((item) => item.id !== saved.id)]
        .sort((a, b) => `${a.subject}:${a.predicate}`.localeCompare(`${b.subject}:${b.predicate}`))
      const laterDraft = cloneDraft(factDraft.value)
      const unchanged = JSON.stringify(laterDraft) === JSON.stringify(snapshot)
      discardSavedScope(requestScope, snapshot)
      if (!recordId) activeFactId.value = saved.id
      const savedBaseline = factToDraft(saved)
      hydratingFact = true
      setBaseline(factScopeKey(projectId, saved.id), savedBaseline)
      factDraft.value = unchanged ? savedBaseline : laterDraft
      hydratingFact = false
      if (!unchanged && isScopeDirty(factScopeKey(projectId, saved.id), laterDraft)) persistDraft(factScopeKey(projectId, saved.id), laterDraft)
      factStatus.value = unchanged ? `事实已保存为 v${saved.version}。` : `事实已保存为 v${saved.version}；后续编辑已保留为本地草稿。`
      await loadFactDetails(projectId, saved.id)
      return true
    } catch (reason) {
      if (isActiveProject(projectId) && selection === factSelectionEpoch) factError.value = reason instanceof Error ? reason.message : '事实保存失败。'
      return false
    } finally {
      if (selection === factSelectionEpoch) isSavingFact.value = false
    }
  }

  async function retractFact(reason: string) {
    factError.value = ''
    const projectId = context.activeProjectId
    const current = activeFact.value
    if (!projectId || !current) { factError.value = '请先选择事实。'; return false }
    if (!reason.trim()) { factError.value = '撤回事实时请填写原因。'; return false }
    if (isRetractingFact.value) return false
    isRetractingFact.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/story-facts/${current.id}/retract`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: current.version, reason: reason.trim() }),
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || (response.status === 409 ? '事实版本已变化，请刷新后重新核对。' : '撤回事实失败。'))
      }
      const saved: StoryFact = await response.json()
      if (!isActiveProject(projectId) || activeFactId.value !== current.id) return false
      facts.value = facts.value.map((item) => item.id === saved.id ? saved : item)
      hydrateFactDraft(saved)
      await loadFactDetails(projectId, saved.id)
      factStatus.value = `事实已撤回（v${saved.version}），历史记录仍保留。`
      return true
    } catch (reasonValue) {
      if (isActiveProject(projectId)) factError.value = reasonValue instanceof Error ? reasonValue.message : '撤回事实失败。'
      return false
    } finally {
      isRetractingFact.value = false
    }
  }

  function validateKnowledgeDraft() {
    const draft = knowledgeDraft.value
    const selectedFact = activeFact.value
    if (!selectedFact) return '请先选择事实。'
    if (knowledgeReadOnly.value || draft.scope === 'world_truth') return '世界真相由事实本身派生，不能单独编辑。'
    if (draft.scope === 'character_knowledge' && !draft.character.trim()) return '角色知识必须填写角色。'
    if (!Number.isInteger(draft.known_from_scene) || draft.known_from_scene < selectedFact.valid_from_scene || (selectedFact.valid_to_scene !== null && draft.known_from_scene > selectedFact.valid_to_scene)) return '知情时点必须落在事实有效场景范围内。'
    if (!draft.reason.trim()) return '维护知情范围时请填写原因。'
    return ''
  }

  function knowledgePayload(draft: KnowledgeStateDraft) {
    return {
      scope: draft.scope,
      character: draft.scope === 'character_knowledge' ? draft.character.trim() : '',
      known_from_scene: draft.known_from_scene,
      source_ref: draft.source_ref.trim(), status: draft.status,
    }
  }

  async function saveKnowledge() {
    knowledgeError.value = ''
    knowledgeStatus.value = ''
    const projectId = context.activeProjectId
    const selectedFact = activeFact.value
    const validation = validateKnowledgeDraft()
    if (validation) { knowledgeError.value = validation; return false }
    if (!projectId || !selectedFact || isSavingKnowledge.value) return false
    const selected = activeKnowledge.value
    const selection = knowledgeSelectionEpoch
    const requestScope = knowledgeScopeKey(projectId, selectedFact.id, selected?.id ?? '')
    const snapshot = cloneDraft(knowledgeDraft.value)
    const body = {
      ...knowledgePayload(snapshot), reason: snapshot.reason.trim(),
      ...(selected ? { expected_version: selected.version } : {}),
    }
    isSavingKnowledge.value = true
    try {
      const url = selected
        ? `/projects/${projectId}/story-facts/${selectedFact.id}/knowledge-states/${selected.id}`
        : `/projects/${projectId}/story-facts/${selectedFact.id}/knowledge-states`
      const response = await fetchApi(url, {
        method: selected ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || (response.status === 409 ? '知识版本已变化，请刷新后重新核对。' : '知识状态保存失败。'))
      }
      const saved: KnowledgeState = await response.json()
      if (!isActiveProject(projectId) || selection !== knowledgeSelectionEpoch || activeFactId.value !== selectedFact.id) return false
      discardSavedScope(requestScope, snapshot)
      if (!selected) activeKnowledgeId.value = saved.id
      await loadFactDetails(projectId, selectedFact.id)
      const refreshed = knowledgeStates.value.find((item) => item.id === saved.id) ?? saved
      hydratingKnowledge = true
      const baseline = knowledgeToDraft(refreshed)
      setBaseline(knowledgeScopeKey(projectId, selectedFact.id, saved.id), baseline)
      knowledgeDraft.value = baseline
      hydratingKnowledge = false
      knowledgeStatus.value = `知识状态已保存为 v${saved.version}。`
      return true
    } catch (reason) {
      if (isActiveProject(projectId) && selection === knowledgeSelectionEpoch) knowledgeError.value = reason instanceof Error ? reason.message : '知识状态保存失败。'
      return false
    } finally {
      if (selection === knowledgeSelectionEpoch) isSavingKnowledge.value = false
    }
  }

  async function retractKnowledge(reason: string) {
    knowledgeError.value = ''
    const projectId = context.activeProjectId
    const selectedFact = activeFact.value
    const selected = activeKnowledge.value
    if (!projectId || !selectedFact || !selected) { knowledgeError.value = '请先选择知识状态。'; return false }
    if (selected.scope === 'world_truth') { knowledgeError.value = '世界真相随事实维护，不能单独撤回。'; return false }
    if (!reason.trim()) { knowledgeError.value = '撤回知识状态时请填写原因。'; return false }
    if (isRetractingKnowledge.value) return false
    isRetractingKnowledge.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/story-facts/${selectedFact.id}/knowledge-states/${selected.id}/retract`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_version: selected.version, reason: reason.trim() }),
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || '撤回知识状态失败。')
      }
      const saved: KnowledgeState = await response.json()
      if (!isActiveProject(projectId) || activeFactId.value !== selectedFact.id) return false
      await loadFactDetails(projectId, selectedFact.id)
      selectKnowledge(saved.id)
      knowledgeStatus.value = `知识状态已撤回（v${saved.version}）。`
      return true
    } catch (reasonValue) {
      if (isActiveProject(projectId)) knowledgeError.value = reasonValue instanceof Error ? reasonValue.message : '撤回知识状态失败。'
      return false
    } finally {
      isRetractingKnowledge.value = false
    }
  }

  async function loadStoryState(scenePosition: number, character = '') {
    const epoch = ++previewEpoch
    previewError.value = ''
    previewStatus.value = ''
    const projectId = context.activeProjectId
    if (!projectId) { previewError.value = '请先创建或选择项目。'; return false }
    if (!Number.isInteger(scenePosition) || scenePosition < 0 || scenePosition > 999) {
      previewError.value = '预览场景位置必须是 0–999 的整数。'
      return false
    }
    isLoadingPreview.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/story-state?scene_position=${scenePosition}&character=${encodeURIComponent(character.trim())}`)
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || '场景知识预览加载失败。')
      }
      const loaded: StoryStateResponse = await response.json()
      if (epoch !== previewEpoch || !isActiveProject(projectId)) return false
      storyState.value = loaded
      previewStatus.value = `已按场景 ${scenePosition} 的安全快照预览。`
      return true
    } catch (reason) {
      if (epoch === previewEpoch && isActiveProject(projectId)) previewError.value = reason instanceof Error ? reason.message : '场景知识预览加载失败。'
      return false
    } finally {
      if (epoch === previewEpoch) isLoadingPreview.value = false
    }
  }

  async function load(projectId: string, sceneId = '') {
    controller?.abort()
    const request = new AbortController()
    controller = request
    isLoading.value = true
    error.value = ''
    try {
      const suffix = sceneId ? `?scene_id=${encodeURIComponent(sceneId)}` : ''
      const responses = await Promise.all([
        fetchApi(`/projects/${projectId}/story-threads`, { signal: request.signal }),
        fetchApi(`/projects/${projectId}/narrative/relations`, { signal: request.signal }),
        fetchApi(`/projects/${projectId}/narrative/director${suffix}`, { signal: request.signal }),
        fetchApi(`/projects/${projectId}/story-facts`, { signal: request.signal }),
      ])
      if (responses.some((response) => !response.ok)) throw new Error('Narrative 状态加载失败，请刷新重试。')
      const [loadedThreads, loadedRelations, loadedDirector, loadedFacts] = await Promise.all(responses.map((response) => response.json()))
      if (request.signal.aborted || !isActiveProject(projectId)) return
      threads.value = loadedThreads
      relations.value = loadedRelations
      director.value = loadedDirector
      facts.value = loadedFacts
      if (activeFactId.value && !facts.value.some((item) => item.id === activeFactId.value)) {
        activeFactId.value = ''
        knowledgeStates.value = []
        history.value = []
        hydrateFactDraft(undefined)
        hydrateKnowledgeDraft(undefined)
      }
    } catch (reason) {
      if (!request.signal.aborted && isActiveProject(projectId)) error.value = reason instanceof Error ? reason.message : 'Narrative 状态加载失败。'
    } finally {
      if (!request.signal.aborted) isLoading.value = false
    }
  }

  function reset() {
    controller?.abort()
    factDetailEpoch += 1
    factSelectionEpoch += 1
    knowledgeSelectionEpoch += 1
    previewEpoch += 1
    threads.value = []
    relations.value = []
    director.value = null
    facts.value = []
    activeFactId.value = ''
    knowledgeStates.value = []
    history.value = []
    activeKnowledgeId.value = ''
    hydrateFactDraft(undefined)
    hydrateKnowledgeDraft(undefined)
    storyState.value = null
    error.value = ''
    factError.value = ''
    factStatus.value = ''
    knowledgeError.value = ''
    knowledgeStatus.value = ''
    previewError.value = ''
    previewStatus.value = ''
    isLoading.value = false
    isSavingFact.value = false
    isRetractingFact.value = false
    isLoadingFactDetails.value = false
    isSavingKnowledge.value = false
    isRetractingKnowledge.value = false
    isLoadingPreview.value = false
  }

  function draftSnapshotEntries(): Array<[string, () => unknown]> {
    return [
      [factScopeKey(), () => factDraft.value],
      [knowledgeScopeKey(), () => knowledgeDraft.value],
    ]
  }

  return {
    threads, relations, director, error, isLoading, load, reset,
    facts, activeFactId, activeFact, factDraft, factError, factStatus, isSavingFact, isRetractingFact,
    isLoadingFactDetails, knowledgeStates, history, activeKnowledgeId, activeKnowledge, knowledgeDraft,
    knowledgeError, knowledgeStatus, isSavingKnowledge, isRetractingKnowledge, knowledgeReadOnly,
    storyState, previewError, previewStatus, isLoadingPreview,
    createEmptyFactDraft, createEmptyKnowledgeDraft, factScopeKey, knowledgeScopeKey, draftSnapshotEntries,
    selectFact, startNewFact, saveFact, retractFact, selectKnowledge, startNewKnowledge,
    saveKnowledge, retractKnowledge, loadStoryState, loadFactDetails,
  }
})
