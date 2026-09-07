import { computed, ref, watch } from 'vue'
import { confirmLeave } from '../../composables/useDirtyGuard'
import { useScopedRequest } from '../../composables/useScopedRequest'
import { acknowledgeDraftSave, discardSavedScope, isScopeDirty, persistDraft, queueAutosave, restoreEntryDraft } from '../../services/draftSessions'
import { useGraphStore } from '../graph'
import type { ManuscriptChapter, ManuscriptChapterDraft, SceneContract, SceneDraft, ChapterCompileResponse } from '../../types'
import { useProjectContextStore } from '../projectContext'
import { fetchApi } from '../../api/client'

export function useManuscriptStructure() {
  const context = useProjectContextStore()
  const isActiveProject = (projectId: string) => projectId === context.activeProjectId
  const requestScopes = useScopedRequest()
  const manuscriptChapters = ref<ManuscriptChapter[]>([])
  const activeChapterId = ref('')
  const chapterDraft = ref<ManuscriptChapterDraft>(createEmptyChapterDraft())
  const chapterError = ref('')
  const chapterStatus = ref('')
  const isSavingChapter = ref(false)
  const isDeletingChapter = ref(false)

  // ---- Scene contracts ----
  const sceneContracts = ref<SceneContract[]>([])
  const activeSceneId = ref('')
  const sceneDraft = ref<SceneDraft>(createEmptySceneDraft())
  const sceneError = ref('')
  const sceneStatus = ref('')
  const isSavingScene = ref(false)
  const isDeletingScene = ref(false)
  const isCompilingScene = ref(false)
  const compileResult = ref<ChapterCompileResponse | null>(null)
  let suppressNextChapterSelectionGuard = false
  let suppressNextSceneSelectionGuard = false

  const activeChapter = computed(() =>
    manuscriptChapters.value.find((chapter) => chapter.id === activeChapterId.value)
  )

  const activeSceneContract = computed(() =>
    sceneContracts.value.find((scene) => scene.id === activeSceneId.value)
  )
  const unassignedSceneContracts = computed(() =>
    sceneContracts.value.filter((scene) => !scene.chapter_id)
  )

  const chapterStateLabel = computed(() => {
    if (chapterStatus.value) {
      return chapterStatus.value
    }
    return activeChapter.value ? '编辑章节' : '新建章节'
  })

  const sceneStateLabel = computed(() => {
    if (sceneStatus.value) {
      return sceneStatus.value
    }
    return activeSceneContract.value ? '编辑场景' : '新建场景'
  })
  function createEmptyChapterDraft(): ManuscriptChapterDraft {
    return {
      sequence: 1,
      title: '',
      summary: '',
    }
  }

  function createEmptySceneDraft(): SceneDraft {
    return {
      chapter_id: '',
      sequence: 1,
      title: '',
      pov: '',
      goal: '',
      conflict: '',
      turning_point: '',
      outcome: '',
      required_canon: '',
      forbidden_facts: '',
      information_delta: '',
      character_state_delta: '',
      story_thread_actions: '',
      open_threads: '',
      source_artifact_step: 8,
    }
  }
  function chapterScopeKey(
    projectId = context.activeProjectId,
    id = activeChapterId.value
  ): string {
    return `chapter:${projectId}:${id || 'new'}`
  }

  function sceneScopeKey(
    projectId = context.activeProjectId,
    id = activeSceneId.value
  ): string {
    return `scene:${projectId}:${id || 'new'}`
  }
  watch(chapterDraft, () => queueAutosave(chapterScopeKey(), () => chapterDraft.value), {
    deep: true,
    flush: 'sync',
  })
  watch(sceneDraft, () => queueAutosave(sceneScopeKey(), () => sceneDraft.value), {
    deep: true,
    flush: 'sync',
  })
  let chapterSelectionEpoch = 0
  watch(() => chapterScopeKey(), () => { chapterSelectionEpoch++ }, { flush: 'sync' })

  watch(activeChapterId, (next, prev) => {
    if (suppressNextChapterSelectionGuard) {
      suppressNextChapterSelectionGuard = false
    } else {
      const previousScope = chapterScopeKey(context.activeProjectId, prev)
      if (isScopeDirty(previousScope, chapterDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Chapter 编辑' : '新建 Chapter 表单')) {
          const outgoingDraft = chapterDraft.value
          suppressNextChapterSelectionGuard = true
          activeChapterId.value = prev
          chapterDraft.value = outgoingDraft
          return
        }
        persistDraft(previousScope, chapterDraft.value)
      }
    }
    chapterError.value = ''
    chapterStatus.value = ''
    const selected = activeChapter.value
    const baselineDraft = selected
      ? {
          sequence: selected.sequence,
          title: selected.title,
          summary: selected.summary,
        }
      : createEmptyChapterDraft()
    chapterDraft.value = baselineDraft
    restoreEntryDraft<ManuscriptChapterDraft>(chapterScopeKey(), baselineDraft, (cached) => {
      chapterDraft.value = cached
    }, (message) => {
      chapterStatus.value = message
    })
  }, { flush: 'sync' })

  let sceneSelectionEpoch = 0
  watch(() => sceneScopeKey(), () => { sceneSelectionEpoch++ }, { flush: 'sync' })

  watch(activeSceneId, (next, prev) => {
    if (suppressNextSceneSelectionGuard) {
      suppressNextSceneSelectionGuard = false
    } else {
      const previousScope = sceneScopeKey(context.activeProjectId, prev)
      if (isScopeDirty(previousScope, sceneDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Scene Contract 编辑' : '新建 Scene 表单')) {
          const outgoingDraft = sceneDraft.value
          suppressNextSceneSelectionGuard = true
          activeSceneId.value = prev
          sceneDraft.value = outgoingDraft
          return
        }
        persistDraft(previousScope, sceneDraft.value)
      }
    }
    sceneError.value = ''
    sceneStatus.value = ''
    compileResult.value = null
    const selected = activeSceneContract.value
    const baselineDraft = selected
      ? {
          chapter_id: selected.chapter_id,
          sequence: selected.sequence,
          title: selected.title,
          pov: selected.pov,
          goal: selected.goal,
          conflict: selected.conflict,
          turning_point: selected.turning_point,
          outcome: selected.outcome,
          required_canon: selected.required_canon,
          forbidden_facts: selected.forbidden_facts,
          information_delta: selected.information_delta,
          character_state_delta: selected.character_state_delta,
          story_thread_actions: selected.story_thread_actions,
          open_threads: selected.open_threads,
          source_artifact_step: selected.source_artifact_step,
        }
      : createEmptySceneDraft()
    sceneDraft.value = baselineDraft
    restoreEntryDraft<SceneDraft>(sceneScopeKey(), baselineDraft, (cached) => {
      sceneDraft.value = cached
    }, (message) => {
      sceneStatus.value = message
    })
  }, { flush: 'sync' })
  async function loadManuscriptChapters(projectId = context.activeProjectId) {
    chapterError.value = ''
    if (!projectId) {
      manuscriptChapters.value = []
      activeChapterId.value = ''
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/chapters`)
      if (!response.ok) {
        throw new Error('Could not load manuscript chapters')
      }
      const chapters = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptChapters.value = chapters
      if (!manuscriptChapters.value.some((chapter) => chapter.id === activeChapterId.value)) {
        activeChapterId.value = manuscriptChapters.value[0]?.id ?? ''
      }
    } catch {
      chapterError.value = 'Manuscript chapters could not be loaded.'
    }
  }
  function startNewChapter() {
    activeChapterId.value = ''
    if (activeChapterId.value) return
    chapterDraft.value = {
      ...createEmptyChapterDraft(),
      sequence: manuscriptChapters.value.length + 1,
    }
    chapterStatus.value = ''
    chapterError.value = ''
  }

  async function saveChapter() {
    chapterError.value = ''
    chapterStatus.value = ''
    const projectId = context.activeProjectId
    const title = chapterDraft.value.title.trim()

    if (!projectId) {
      chapterError.value = '请先创建或选择项目。'
      return
    }

    if (!title) {
      chapterError.value = 'Chapter title is required.'
      return
    }

    if (isSavingChapter.value) return
    const recordId = activeChapterId.value
    const requestScope = chapterScopeKey(projectId, recordId)
    const requestEpoch = chapterSelectionEpoch
    const snapshot = { ...chapterDraft.value }
    isSavingChapter.value = true
    try {
      const body = JSON.stringify({
        sequence: chapterDraft.value.sequence,
        title,
        summary: chapterDraft.value.summary.trim(),
      })
      const url = recordId
        ? `/projects/${projectId}/manuscript/chapters/${recordId}`
        : `/projects/${projectId}/manuscript/chapters`
      const response = await fetchApi(url, {
        method: recordId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Chapter')
      }
      const saved: ManuscriptChapter = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptChapters.value = [
        ...manuscriptChapters.value.filter((chapter) => chapter.id !== saved.id),
        saved,
      ].sort((left, right) => left.sequence - right.sequence)
      if (requestEpoch !== chapterSelectionEpoch) return
      const current = { ...chapterDraft.value }
      acknowledgeDraftSave(requestScope, snapshot, current)
      if (activeChapterId.value !== saved.id) {
        // Only an actual selection change may bypass its guard.
        suppressNextChapterSelectionGuard = true
        activeChapterId.value = saved.id
        chapterDraft.value = current
        discardSavedScope(requestScope, snapshot)
        acknowledgeDraftSave(chapterScopeKey(projectId, saved.id), snapshot, current)
      }
      chapterStatus.value = 'Chapter saved.'
    } catch {
      if (!isActiveProject(projectId) || requestEpoch !== chapterSelectionEpoch) return
      chapterError.value = 'Chapter save failed. Check for duplicate sequence numbers.'
    } finally {
      isSavingChapter.value = false
    }
  }

  async function deleteChapter() {
    chapterError.value = ''
    chapterStatus.value = ''
    const projectId = context.activeProjectId
    const chapterId = activeChapterId.value

    if (!projectId || !chapterId) {
      chapterError.value = 'Select a Chapter first.'
      return
    }

    isDeletingChapter.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/chapters/${chapterId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Chapter')
      }
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptChapters.value = manuscriptChapters.value.filter((chapter) => chapter.id !== chapterId)
      sceneContracts.value = sceneContracts.value.map((scene) =>
        scene.chapter_id === chapterId ? { ...scene, chapter_id: '' } : scene
      )
      startNewChapter()
      chapterStatus.value = 'Chapter deleted. Its scenes are now unassigned.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      chapterError.value = 'Chapter delete failed. Check that the API is running.'
    } finally {
      isDeletingChapter.value = false
    }
  }

  // ---- Scene contracts ----

  function startNewSceneContract() {
    activeSceneId.value = ''
    if (activeSceneId.value) return
    sceneDraft.value = {
      ...createEmptySceneDraft(),
      chapter_id: activeChapterId.value,
      sequence: sceneContracts.value.length + 1,
    }
    sceneStatus.value = ''
    sceneError.value = ''
    compileResult.value = null
  }

  async function saveSceneContract() {
    sceneError.value = ''
    sceneStatus.value = ''
    const projectId = context.activeProjectId
    const title = sceneDraft.value.title.trim()

    if (!projectId) {
      sceneError.value = '请先创建或选择项目。'
      return
    }

    if (!title) {
      sceneError.value = 'Scene title is required.'
      return
    }

    if (isSavingScene.value) return
    const recordId = activeSceneId.value
    const requestScope = sceneScopeKey(projectId, recordId)
    const requestEpoch = sceneSelectionEpoch
    const snapshot = { ...sceneDraft.value }
    isSavingScene.value = true
    try {
      const body = JSON.stringify({
        ...sceneDraft.value,
        chapter_id: sceneDraft.value.chapter_id.trim(),
        title,
        pov: sceneDraft.value.pov.trim(),
        goal: sceneDraft.value.goal.trim(),
        conflict: sceneDraft.value.conflict.trim(),
        turning_point: sceneDraft.value.turning_point.trim(),
        outcome: sceneDraft.value.outcome.trim(),
        required_canon: sceneDraft.value.required_canon.trim(),
        forbidden_facts: sceneDraft.value.forbidden_facts.trim(),
        information_delta: sceneDraft.value.information_delta.trim(),
        character_state_delta: sceneDraft.value.character_state_delta.trim(),
        story_thread_actions: sceneDraft.value.story_thread_actions.trim(),
        open_threads: sceneDraft.value.open_threads.trim(),
      })
      const url = recordId
        ? `/projects/${projectId}/scene-contracts/${recordId}`
        : `/projects/${projectId}/scene-contracts`
      const response = await fetchApi(url, {
        method: recordId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Scene contract')
      }
      const saved = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      sceneContracts.value = [
        ...sceneContracts.value.filter((scene) => scene.id !== saved.id),
        saved,
      ].sort((left, right) => left.sequence - right.sequence)
      if (requestEpoch !== sceneSelectionEpoch) return
      const current = { ...sceneDraft.value }
      acknowledgeDraftSave(requestScope, snapshot, current)
      if (activeSceneId.value !== saved.id) {
        // Only an actual selection change may bypass its guard.
        suppressNextSceneSelectionGuard = true
        activeSceneId.value = saved.id
        sceneDraft.value = current
        discardSavedScope(requestScope, snapshot)
        acknowledgeDraftSave(sceneScopeKey(projectId, saved.id), snapshot, current)
      }
      sceneStatus.value = 'Scene contract saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      if (!isActiveProject(projectId) || requestEpoch !== sceneSelectionEpoch) return
      sceneError.value = 'Scene save failed. Check for duplicate sequence numbers.'
    } finally {
      isSavingScene.value = false
    }
  }

  async function deleteSceneContract() {
    sceneError.value = ''
    sceneStatus.value = ''
    const projectId = context.activeProjectId
    const sceneId = activeSceneId.value

    if (!projectId || !sceneId) {
      sceneError.value = '请先选择场景。'
      return
    }

    isDeletingScene.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/scene-contracts/${sceneId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Scene contract')
      }
      if (!isActiveProject(projectId)) {
        return
      }
      sceneContracts.value = sceneContracts.value.filter((scene) => scene.id !== sceneId)
      startNewSceneContract()
      sceneStatus.value = 'Scene contract deleted.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      sceneError.value = 'Scene delete failed. Check that the API is running.'
    } finally {
      isDeletingScene.value = false
    }
  }

  async function compileSceneContract() {
    sceneError.value = ''
    sceneStatus.value = ''
    compileResult.value = null
    const projectId = context.activeProjectId
    const sceneId = activeSceneId.value

    if (!projectId || !sceneId) {
      sceneError.value = '请先选择场景。'
      return
    }

    isCompilingScene.value = true
    const compileScope = requestScopes.begin(projectId, 'scene-compile', sceneId)
    try {
      const response = await fetchApi(`/projects/${projectId}/scene-contracts/${sceneId}/compile`, {
        method: 'POST',
      })
      if (!response.ok) {
        throw new Error('Could not compile Scene contract')
      }
      const result = await response.json()
      if (!isActiveProject(projectId) || !requestScopes.isCurrent(compileScope)) {
        return
      }
      compileResult.value = result
      sceneStatus.value = 'Scene compiled.'
    } catch {
      sceneError.value = 'Scene compile failed. Check that the API is running.'
    } finally {
      isCompilingScene.value = false
    }
  }

  async function refreshSceneContracts(projectId: string) {
    const response = await fetchApi(`/projects/${projectId}/scene-contracts`)
    if (!response.ok) {
      return
    }
    const contracts = await response.json()
    if (!isActiveProject(projectId)) {
      return
    }
    sceneContracts.value = [...contracts].sort(
      (left, right) => left.sequence - right.sequence
    )
  }

  function scenesForChapter(chapterId: string) {
    return sceneContracts.value.filter((scene) => scene.chapter_id === chapterId)
  }

  function chapterTitleForScene(sceneId: string) {
    const scene = sceneContracts.value.find((item) => item.id === sceneId)
    const chapter = manuscriptChapters.value.find((item) => item.id === scene?.chapter_id)
    return chapter ? `Chapter ${chapter.sequence}: ${chapter.title}` : '未分章'
  }

  function resetStructure() {
    chapterError.value = ''
    chapterStatus.value = ''
    sceneError.value = ''
    sceneStatus.value = ''
    manuscriptChapters.value = []
    sceneContracts.value = []
    compileResult.value = null
    activeChapterId.value = ''
    activeSceneId.value = ''
    chapterDraft.value = createEmptyChapterDraft()
    sceneDraft.value = createEmptySceneDraft()
  }

  function structureDraftSnapshotEntries(): Array<[string, () => unknown]> {
    return [
      [chapterScopeKey(), () => chapterDraft.value],
      [sceneScopeKey(), () => sceneDraft.value],
    ]
  }

  return {
    manuscriptChapters,
    activeChapterId,
    chapterDraft,
    chapterError,
    chapterStatus,
    isSavingChapter,
    isDeletingChapter,
    sceneContracts,
    activeSceneId,
    sceneDraft,
    sceneError,
    sceneStatus,
    isSavingScene,
    isDeletingScene,
    isCompilingScene,
    compileResult,
    activeChapter,
    activeSceneContract,
    unassignedSceneContracts,
    chapterStateLabel,
    sceneStateLabel,
    createEmptyChapterDraft,
    createEmptySceneDraft,
    chapterScopeKey,
    sceneScopeKey,
    loadManuscriptChapters,
    startNewChapter,
    startNewSceneContract,
    saveChapter,
    deleteChapter,
    saveSceneContract,
    deleteSceneContract,
    compileSceneContract,
    refreshSceneContracts,
    scenesForChapter,
    chapterTitleForScene,
    resetStructure,
    structureDraftSnapshotEntries,
  }
}
