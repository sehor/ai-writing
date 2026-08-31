import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { readErrorDetail } from '../api/errors'
import { useEditorSessionStore } from './editorSession'
import { confirmLeave } from '../composables/useDirtyGuard'
import { useScopedRequest } from '../composables/useScopedRequest'
import { clearDraft } from '../services/draftCache'
import {
  formatSavedAt,
  isScopeDirty,
  persistDraft,
  queueAutosave,
  restoreCachedDraft,
  restoreEntryDraft,
  setBaseline,
} from '../services/draftSessions'
import type {
  SceneContract,
  SceneDraft,
  ManuscriptChapter,
  ManuscriptChapterDraft,
  ChapterCompileResponse,
  ManuscriptProposalStatus,
  ManuscriptProposal,
  ManuscriptScene,
  ManuscriptRevision,
  ManuscriptRevisionDiff,
  ManuscriptExport,
} from '../types'
import { useGraphStore } from './graph'
import { useReviewsStore } from './reviews'
import { useWorkspaceStore } from './workspace'
import { useProposalDraftStore } from './proposalDraft'
import type { WorkspaceShell } from './workspaceShell'

type ManuscriptEditDraft = { title: string; content: string; expected_scene_version: number | null }

/** Manuscript domain: chapters, scene contracts, review proposals, and the
 *  accepted scenes / revisions / diff / export pipeline. */
export const useManuscriptStore = defineStore('manuscript', () => {
  // Lazy, explicitly-typed access keeps the store type graph acyclic.
  function ws(): WorkspaceShell {
    return useWorkspaceStore()
  }
  const editorSession = useEditorSessionStore()
  const requestScopes = useScopedRequest()

  // ---- Chapters ----
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

  // ---- Review proposals ----
  const manuscriptProposals = ref<ManuscriptProposal[]>([])
  const activeProposalId = ref('')
  const manuscriptError = ref('')
  const manuscriptStatus = ref('')
  const isCreatingProposal = ref(false)
  const isCreatingProviderProposal = ref(false)
  const isUpdatingProposal = ref(false)

  // ---- Accepted scenes / revisions / export / inline editing ----
  const manuscriptScenes = ref<ManuscriptScene[]>([])
  const manuscriptRevisions = ref<ManuscriptRevision[]>([])
  const revisionDiff = ref<ManuscriptRevisionDiff | null>(null)
  const diffLeftRevisionId = ref('')
  const diffRightRevisionId = ref('')
  const isLoadingDiff = ref(false)
  const isRestoringRevision = ref(false)
  const manuscriptExport = ref<ManuscriptExport | null>(null)
  const isExportingManuscript = ref(false)
  const isSavingManuscriptScene = ref(false)
  const editingManuscriptSceneId = ref('')
  const manuscriptEditTitle = ref('')
  const manuscriptEditContent = ref('')
  const manuscriptEditVersion = ref<number | null>(null)
  const manuscriptSaveConflict = ref(false)
  const manuscriptEditReviewReady = ref(false)
  const isRefreshingManuscriptEdit = ref(false)
  let manuscriptEditProjectId = ''
  let manuscriptEditSession = 0
  let hydratingManuscriptEdit = false
  const editingManuscriptScene = computed(() =>
    manuscriptScenes.value.find((scene) => scene.scene_id === editingManuscriptSceneId.value)
  )
  const manuscriptEditNeedsReview = computed(() =>
    !!editingManuscriptSceneId.value && (manuscriptSaveConflict.value ||
      manuscriptEditVersion.value === null ||
      manuscriptEditVersion.value !== editingManuscriptScene.value?.version)
  )

  /** Set while a save/programmatic change moves a selection itself. */
  let suppressNextSelectionGuard = false

  const activeChapter = computed(() =>
    manuscriptChapters.value.find((chapter) => chapter.id === activeChapterId.value)
  )

  const activeSceneContract = computed(() =>
    sceneContracts.value.find((scene) => scene.id === activeSceneId.value)
  )

  const activeProposal = computed(() =>
    manuscriptProposals.value.find((proposal) => proposal.id === activeProposalId.value)
  )

  const pendingProposalCount = computed(
    () => manuscriptProposals.value.filter((proposal) => proposal.status === 'pending_review').length
  )

  const unassignedSceneContracts = computed(() =>
    sceneContracts.value.filter((scene) => !scene.chapter_id)
  )

  const chapterStateLabel = computed(() => {
    if (chapterStatus.value) {
      return chapterStatus.value
    }
    return activeChapter.value ? 'Editing Chapter' : 'New Chapter'
  })

  const sceneStateLabel = computed(() => {
    if (sceneStatus.value) {
      return sceneStatus.value
    }
    return activeSceneContract.value ? 'Editing Scene contract' : 'New Scene contract'
  })

  const acceptedSceneCount = computed(() => manuscriptScenes.value.length)

  const revisionCount = computed(() => manuscriptRevisions.value.length)

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
      required_canon: '',
      forbidden_facts: '',
      open_threads: '',
      source_artifact_step: 8,
    }
  }

  function isActiveProject(projectId: string) {
    return projectId === ws().activeProjectId
  }

  function chapterScopeKey(
    projectId = ws().activeProjectId,
    id = activeChapterId.value
  ): string {
    return `chapter:${projectId}:${id || 'new'}`
  }

  function sceneScopeKey(
    projectId = ws().activeProjectId,
    id = activeSceneId.value
  ): string {
    return `scene:${projectId}:${id || 'new'}`
  }

  function manuscriptEditScopeKey(
    projectId = ws().activeProjectId,
    sceneId = editingManuscriptSceneId.value
  ): string {
    return `manuscript:${projectId}:${sceneId || 'new'}`
  }

  function currentManuscriptEdits(): ManuscriptEditDraft {
    return {
      title: manuscriptEditTitle.value,
      content: manuscriptEditContent.value,
      expected_scene_version: manuscriptEditVersion.value,
    }
  }

  watch(chapterDraft, () => queueAutosave(chapterScopeKey(), () => chapterDraft.value), {
    deep: true,
  })
  watch(sceneDraft, () => queueAutosave(sceneScopeKey(), () => sceneDraft.value), {
    deep: true,
  })
  watch(
    [manuscriptEditTitle, manuscriptEditContent, manuscriptEditVersion],
    () => {
      if (hydratingManuscriptEdit || !editingManuscriptSceneId.value) return
      const key = manuscriptEditScopeKey(manuscriptEditProjectId)
      const snapshot = currentManuscriptEdits()
      if (isScopeDirty(key, snapshot)) editorSession.markDirty(key)
      else editorSession.markClean(key)
      // A delayed autosave must not read a different scene or project.
      queueAutosave(key, () => snapshot)
    },
    { flush: 'sync' }
  )

  watch(activeChapterId, (next, prev) => {
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else {
      const previousScope = chapterScopeKey(ws().activeProjectId, prev)
      if (isScopeDirty(previousScope, chapterDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Chapter 编辑' : '新建 Chapter 表单')) {
          suppressNextSelectionGuard = true
          activeChapterId.value = prev
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
    restoreEntryDraft<ManuscriptChapterDraft>(chapterScopeKey(), baselineDraft, (cached) => {
      chapterDraft.value = cached
    }, (message) => {
      chapterStatus.value = message
    })
  })

  watch(activeSceneId, (next, prev) => {
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else {
      const previousScope = sceneScopeKey(ws().activeProjectId, prev)
      if (isScopeDirty(previousScope, sceneDraft.value)) {
        if (!confirmLeave(previousScope, prev ? 'Scene Contract 编辑' : '新建 Scene 表单')) {
          suppressNextSelectionGuard = true
          activeSceneId.value = prev
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
          required_canon: selected.required_canon,
          forbidden_facts: selected.forbidden_facts,
          open_threads: selected.open_threads,
          source_artifact_step: selected.source_artifact_step,
        }
      : createEmptySceneDraft()
    restoreEntryDraft<SceneDraft>(sceneScopeKey(), baselineDraft, (cached) => {
      sceneDraft.value = cached
    }, (message) => {
      sceneStatus.value = message
    })
  })

  // ---- Loaders ----

  async function loadManuscriptProposals(projectId = ws().activeProject?.id) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptProposals.value = []
      activeProposalId.value = ''
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/proposals`)
      if (!response.ok) {
        throw new Error('Could not load manuscript proposals')
      }
      const proposals = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptProposals.value = proposals
      if (!manuscriptProposals.value.some((proposal) => proposal.id === activeProposalId.value)) {
        activeProposalId.value = manuscriptProposals.value[0]?.id ?? ''
      }
    } catch {
      manuscriptError.value = 'Manuscript proposals could not be loaded.'
    }
  }

  async function loadManuscriptChapters(projectId = ws().activeProject?.id) {
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

  async function loadManuscriptScenes(projectId = ws().activeProject?.id) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptScenes.value = []
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/scenes`)
      if (!response.ok) {
        throw new Error('Could not load manuscript scenes')
      }
      const scenes = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptScenes.value = scenes
    } catch {
      manuscriptError.value = 'Accepted manuscript scenes could not be loaded.'
    }
  }

  async function loadManuscriptRevisions(projectId = ws().activeProject?.id) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptRevisions.value = []
      revisionDiff.value = null
      diffLeftRevisionId.value = ''
      diffRightRevisionId.value = ''
      return
    }

    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/revisions`)
      if (!response.ok) {
        throw new Error('Could not load manuscript revisions')
      }
      const revisions = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptRevisions.value = revisions
      syncRevisionCompareSelection()
    } catch {
      manuscriptError.value = 'Manuscript revision history could not be loaded.'
    }
  }

  function syncRevisionCompareSelection() {
    const revisions = manuscriptRevisions.value
    if (revisions.length === 0) {
      diffLeftRevisionId.value = ''
      diffRightRevisionId.value = ''
      revisionDiff.value = null
      return
    }
    if (!revisions.some((revision) => revision.id === diffRightRevisionId.value)) {
      diffRightRevisionId.value = revisions[0].id
    }
    if (!revisions.some((revision) => revision.id === diffLeftRevisionId.value)) {
      diffLeftRevisionId.value = revisions[1]?.id ?? revisions[0].id
    }
  }

  // ---- Chapters ----

  function startNewChapter() {
    activeChapterId.value = ''
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
    const projectId = ws().activeProject?.id
    const title = chapterDraft.value.title.trim()

    if (!projectId) {
      chapterError.value = 'Create or select a project first.'
      return
    }

    if (!title) {
      chapterError.value = 'Chapter title is required.'
      return
    }

    isSavingChapter.value = true
    try {
      const body = JSON.stringify({
        sequence: chapterDraft.value.sequence,
        title,
        summary: chapterDraft.value.summary.trim(),
      })
      const url = activeChapterId.value
        ? `/projects/${projectId}/manuscript/chapters/${activeChapterId.value}`
        : `/projects/${projectId}/manuscript/chapters`
      const response = await fetchApi(url, {
        method: activeChapterId.value ? 'PUT' : 'POST',
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
      clearDraft(chapterScopeKey(projectId, activeChapterId.value))
      suppressNextSelectionGuard = true
      activeChapterId.value = saved.id
      chapterStatus.value = 'Chapter saved.'
    } catch {
      chapterError.value = 'Chapter save failed. Check for duplicate sequence numbers.'
    } finally {
      isSavingChapter.value = false
    }
  }

  async function deleteChapter() {
    chapterError.value = ''
    chapterStatus.value = ''
    const projectId = ws().activeProject?.id
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
    const projectId = ws().activeProject?.id
    const title = sceneDraft.value.title.trim()

    if (!projectId) {
      sceneError.value = 'Create or select a project first.'
      return
    }

    if (!title) {
      sceneError.value = 'Scene title is required.'
      return
    }

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
        required_canon: sceneDraft.value.required_canon.trim(),
        forbidden_facts: sceneDraft.value.forbidden_facts.trim(),
        open_threads: sceneDraft.value.open_threads.trim(),
      })
      const url = activeSceneId.value
        ? `/projects/${projectId}/scene-contracts/${activeSceneId.value}`
        : `/projects/${projectId}/scene-contracts`
      const response = await fetchApi(url, {
        method: activeSceneId.value ? 'PUT' : 'POST',
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
      clearDraft(sceneScopeKey(projectId, activeSceneId.value))
      suppressNextSelectionGuard = true
      activeSceneId.value = saved.id
      sceneStatus.value = 'Scene contract saved.'
      await useGraphStore().loadGraphAnalysis(projectId)
    } catch {
      sceneError.value = 'Scene save failed. Check for duplicate sequence numbers.'
    } finally {
      isSavingScene.value = false
    }
  }

  async function deleteSceneContract() {
    sceneError.value = ''
    sceneStatus.value = ''
    const projectId = ws().activeProject?.id
    const sceneId = activeSceneId.value

    if (!projectId || !sceneId) {
      sceneError.value = 'Select a Scene contract first.'
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
    const projectId = ws().activeProject?.id
    const sceneId = activeSceneId.value

    if (!projectId || !sceneId) {
      sceneError.value = 'Select a Scene contract first.'
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
    return chapter ? `Chapter ${chapter.sequence}: ${chapter.title}` : 'Unassigned'
  }

  // ---- Review proposals ----

  async function createProposalFromScene(provider = false) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = ws().activeProject?.id
    const sceneId = activeSceneId.value

    if (!projectId || !sceneId) {
      manuscriptError.value = 'Select a Scene contract first.'
      return
    }

    const loadingFlag = provider ? isCreatingProviderProposal : isCreatingProposal
    loadingFlag.value = true
    try {
      const providerPath = provider ? '/provider' : ''
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/proposals/from-scene/${sceneId}${providerPath}`,
        { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not create manuscript proposal')
      }
      const created: ManuscriptProposal = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptProposals.value = [
        created,
        ...manuscriptProposals.value.filter((proposal) => proposal.id !== created.id),
      ]
      activeProposalId.value = created.id
      manuscriptStatus.value = provider
        ? 'Provider proposal created for review.'
        : 'Proposal created for review.'
    } catch (error) {
      manuscriptError.value =
        error instanceof Error
          ? `Proposal creation failed. ${error.message}`
          : 'Proposal creation failed. Check that the API is running.'
    } finally {
      loadingFlag.value = false
    }
  }

  /** Every committed revision refreshes the same authoring/review surfaces. */
  async function refreshCommittedRevision(projectId: string) {
    const reviews = useReviewsStore()
    await Promise.all([
      loadManuscriptScenes(projectId),
      loadManuscriptRevisions(projectId),
      reviews.loadWritebackProposals(projectId),
    ])
    if (!isActiveProject(projectId)) return
    await Promise.all([
      reviews.loadPostAcceptAnalysisJobs(projectId),
      reviews.showLatestConsistencyReport(projectId),
    ])
  }

  async function updateProposalStatus(proposalId: string, status: ManuscriptProposalStatus) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = ws().activeProject?.id

    if (!projectId) {
      manuscriptError.value = 'Create or select a project first.'
      return
    }

    const draft = useProposalDraftStore()
    if (status === 'accepted' && (draft.projectId !== projectId || draft.proposalId !== proposalId || !draft.title.trim() || !draft.content.trim())) {
      manuscriptError.value = '请打开草稿并填写标题和正文后再接受。'
      return
    }

    isUpdatingProposal.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/proposals/${proposalId}/${status === 'accepted' ? 'accept' : 'status'}`,
        {
          method: status === 'accepted' ? 'POST' : 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(status === 'accepted' ? draft.snapshot() : { status }),
        }
      )
      if (!response.ok) {
        if (response.status === 409 && status === 'accepted') await loadManuscriptScenes(projectId)
        throw new Error((await readErrorDetail(response)).message || 'Could not update manuscript proposal')
      }
      const updated: ManuscriptProposal = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptProposals.value = manuscriptProposals.value.map((proposal) =>
        proposal.id === updated.id ? updated : proposal
      )
      if (status === 'accepted') {
        draft.committed()
        await refreshCommittedRevision(projectId)
        if (!isActiveProject(projectId)) {
          return
        }
      }
      activeProposalId.value = updated.id
      manuscriptStatus.value =
        status === 'accepted'
          ? 'Proposal accepted. Automatic analysis has been scheduled.'
          : 'Proposal rejected.'
    } catch (error) {
      manuscriptError.value = error instanceof Error ? error.message : 'Proposal update failed. Check that the API is running.'
    } finally {
      isUpdatingProposal.value = false
    }
  }

  // ---- Accepted scenes / revisions / export / inline editing ----

  async function loadRevisionDiff() {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    revisionDiff.value = null
    const projectId = ws().activeProject?.id

    if (!projectId || !diffLeftRevisionId.value || !diffRightRevisionId.value) {
      manuscriptError.value = 'Select two revisions to compare.'
      return
    }

    isLoadingDiff.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/revisions/${diffLeftRevisionId.value}/diff/${diffRightRevisionId.value}`
      )
      if (!response.ok) {
        throw new Error('Could not load revision diff')
      }
      const diff = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      revisionDiff.value = diff
      manuscriptStatus.value = 'Revision diff loaded.'
    } catch {
      manuscriptError.value = 'Revision diff failed. Check that the API is running.'
    } finally {
      isLoadingDiff.value = false
    }
  }

  async function restoreRevision(revisionId: string) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = ws().activeProject?.id

    if (!projectId) {
      manuscriptError.value = 'Create or select a project first.'
      return
    }

    isRestoringRevision.value = true
    try {
      const response = await fetchApi(
        `/projects/${projectId}/manuscript/revisions/${revisionId}/restore`,
        { method: 'POST' }
      )
      if (!response.ok) {
        throw new Error('Could not restore revision')
      }
      if (!isActiveProject(projectId)) {
        return
      }
      await refreshCommittedRevision(projectId)
      if (!isActiveProject(projectId)) {
        return
      }
      revisionDiff.value = null
      manuscriptStatus.value = 'Revision restored as a new current version.'
    } catch {
      manuscriptError.value = 'Revision restore failed. Check that the API is running.'
    } finally {
      isRestoringRevision.value = false
    }
  }

  async function exportManuscript() {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    manuscriptExport.value = null
    const projectId = ws().activeProject?.id

    if (!projectId) {
      manuscriptError.value = 'Create or select a project first.'
      return
    }

    isExportingManuscript.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/export`)
      if (!response.ok) {
        throw new Error('Could not export manuscript')
      }
      const exported = await response.json()
      if (!isActiveProject(projectId)) {
        return
      }
      manuscriptExport.value = exported
      manuscriptStatus.value = 'Manuscript export generated.'
    } catch {
      manuscriptError.value = 'Manuscript export failed. Check that the API is running.'
    } finally {
      isExportingManuscript.value = false
    }
  }

  function startEditingManuscriptScene(scene: ManuscriptScene) {
    if (isSavingManuscriptScene.value) return
    const currentScope = manuscriptEditScopeKey(manuscriptEditProjectId)
    if (
      editingManuscriptSceneId.value &&
      isScopeDirty(currentScope, currentManuscriptEdits())
    ) {
      if (!confirmLeave(currentScope, `场景 ${editingManuscriptSceneId.value} 的正文编辑`)) {
        return
      }
      persistDraft(currentScope, currentManuscriptEdits())
    }
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    hydratingManuscriptEdit = true
    manuscriptEditSession++
    manuscriptEditProjectId = ws().activeProjectId
    manuscriptSaveConflict.value = false
    manuscriptEditReviewReady.value = true
    isRefreshingManuscriptEdit.value = false
    editingManuscriptSceneId.value = scene.scene_id
    const nextScope = manuscriptEditScopeKey(ws().activeProjectId, scene.scene_id)
    const baseline = { title: scene.title, content: scene.content, expected_scene_version: scene.version }
    setBaseline(nextScope, baseline)
    const cached = restoreCachedDraft<ManuscriptEditDraft>(nextScope)
    if (cached && typeof cached.value?.title === 'string' && typeof cached.value.content === 'string') {
      manuscriptEditTitle.value = cached.value.title
      manuscriptEditContent.value = cached.value.content
      const version = cached.value.expected_scene_version
      manuscriptEditVersion.value = typeof version === 'number' && Number.isInteger(version) && version >= 1 ? version : null
      editorSession.markDirty(nextScope, cached.savedAt)
      manuscriptStatus.value = `已恢复本地草稿（自动保存于 ${formatSavedAt(cached.savedAt)}）`
    } else {
      manuscriptEditTitle.value = scene.title
      manuscriptEditContent.value = scene.content
      manuscriptEditVersion.value = scene.version
    }
    hydratingManuscriptEdit = false
  }

  function cancelEditingManuscriptScene() {
    const key = manuscriptEditScopeKey(manuscriptEditProjectId)
    if (editingManuscriptSceneId.value && isScopeDirty(key, currentManuscriptEdits())) {
      persistDraft(key, currentManuscriptEdits())
    }
    hydratingManuscriptEdit = true
    manuscriptEditSession++
    editingManuscriptSceneId.value = ''
    manuscriptEditTitle.value = ''
    manuscriptEditContent.value = ''
    manuscriptEditVersion.value = null
    manuscriptEditProjectId = ''
    manuscriptSaveConflict.value = false
    manuscriptEditReviewReady.value = false
    isRefreshingManuscriptEdit.value = false
    isSavingManuscriptScene.value = false
    hydratingManuscriptEdit = false
  }

  async function refreshManuscriptEditConflict() {
    if (!editingManuscriptSceneId.value || isRefreshingManuscriptEdit.value) return
    const projectId = manuscriptEditProjectId
    const session = manuscriptEditSession
    manuscriptEditReviewReady.value = false
    isRefreshingManuscriptEdit.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/scenes`)
      if (!response.ok) throw new Error('Could not load current text')
      const scenes: ManuscriptScene[] = await response.json()
      if (session !== manuscriptEditSession || !isActiveProject(projectId)) return
      manuscriptScenes.value = scenes
      manuscriptEditReviewReady.value = !!editingManuscriptScene.value
      manuscriptError.value = editingManuscriptScene.value
        ? '正文版本已变更。你的编辑已保留，请核对当前正文后再保存。'
        : '当前正文已不存在。你的编辑已保留，请先检查项目状态。'
    } catch {
      if (session === manuscriptEditSession && isActiveProject(projectId)) {
        manuscriptError.value = '读取当前正文失败。你的编辑已保留，请重试读取后再确认版本。'
      }
    } finally {
      if (session === manuscriptEditSession) isRefreshingManuscriptEdit.value = false
    }
  }

  function rebaseManuscriptSceneEdit() {
    if (!manuscriptEditReviewReady.value || isRefreshingManuscriptEdit.value ||
        isSavingManuscriptScene.value || !editingManuscriptScene.value) return
    manuscriptEditVersion.value = editingManuscriptScene.value.version
    manuscriptSaveConflict.value = false
    persistDraft(manuscriptEditScopeKey(manuscriptEditProjectId), currentManuscriptEdits())
    manuscriptError.value = ''
    manuscriptStatus.value = `已确认当前 v${manuscriptEditVersion.value}；编辑内容保留，尚未保存。`
  }

  async function saveManuscriptSceneEdit(sceneId: string) {
    if (isSavingManuscriptScene.value || sceneId !== editingManuscriptSceneId.value) return
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = ws().activeProject?.id
    const title = manuscriptEditTitle.value.trim()
    const content = manuscriptEditContent.value.trim()

    if (!projectId) {
      manuscriptError.value = 'Create or select a project first.'
      return
    }
    if (!title || !content) {
      manuscriptError.value = 'Title and content are required before saving.'
      return
    }
    if (manuscriptEditNeedsReview.value || manuscriptEditVersion.value === null) {
      manuscriptError.value = '请先核对当前正文并确认版本。你的编辑已保留。'
      return
    }

    const session = manuscriptEditSession
    const isCurrentEdit = () => session === manuscriptEditSession && isActiveProject(projectId)
    const snapshot = currentManuscriptEdits()
    persistDraft(manuscriptEditScopeKey(projectId, sceneId), snapshot)
    isSavingManuscriptScene.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/manuscript/scenes/${sceneId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content, expected_scene_version: snapshot.expected_scene_version }),
      })
      if (!isCurrentEdit()) return
      if (response.status === 409) {
        manuscriptSaveConflict.value = true
        await refreshManuscriptEditConflict()
        return
      }
      if (!response.ok) {
        throw new Error('Could not save manuscript scene')
      }
      const updated: ManuscriptScene = await response.json()
      if (!isCurrentEdit()) {
        return
      }
      manuscriptScenes.value = manuscriptScenes.value.map((scene) =>
        scene.scene_id === updated.scene_id ? updated : scene
      )
      const unchanged = JSON.stringify(snapshot) === JSON.stringify(currentManuscriptEdits())
      setBaseline(manuscriptEditScopeKey(projectId, sceneId), snapshot)
      if (unchanged) {
        clearDraft(manuscriptEditScopeKey(projectId, sceneId))
        cancelEditingManuscriptScene()
      } else {
        // Keep any input made while the request was in flight.
        manuscriptEditVersion.value = updated.version
        persistDraft(manuscriptEditScopeKey(projectId, sceneId), currentManuscriptEdits())
      }
      manuscriptExport.value = null
      revisionDiff.value = null
      const savedSession = manuscriptEditSession
      await refreshCommittedRevision(projectId)
      if (!isActiveProject(projectId) || savedSession !== manuscriptEditSession) {
        return
      }
      manuscriptStatus.value = unchanged ? `Scene saved as version ${updated.version}.`
        : `已保存 v${updated.version}；后续编辑已保留，尚未保存。`
    } catch {
      if (isCurrentEdit()) manuscriptError.value = '正文保存失败。你的编辑已保留，请检查 API 后重试。'
    } finally {
      if (session === manuscriptEditSession) isSavingManuscriptScene.value = false
    }
  }

  function revisionLabel(revision: ManuscriptRevision) {
    return `${revision.title} v${revision.version}`
  }

  /** Drop project-scoped state before the workspace loads another project. */
  function resetProjectState() {
    cancelEditingManuscriptScene()
    chapterError.value = ''
    chapterStatus.value = ''
    sceneError.value = ''
    sceneStatus.value = ''
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    manuscriptChapters.value = []
    sceneContracts.value = []
    manuscriptProposals.value = []
    manuscriptScenes.value = []
    manuscriptRevisions.value = []
    compileResult.value = null
    revisionDiff.value = null
    manuscriptExport.value = null
    activeChapterId.value = ''
    activeSceneId.value = ''
    activeProposalId.value = ''
    diffLeftRevisionId.value = ''
    diffRightRevisionId.value = ''
    editingManuscriptSceneId.value = ''
    manuscriptEditTitle.value = ''
    manuscriptEditContent.value = ''
    chapterDraft.value = createEmptyChapterDraft()
    sceneDraft.value = createEmptySceneDraft()
  }

  function draftSnapshotEntries(): Array<[string, () => unknown]> {
    return [
      [chapterScopeKey(), () => chapterDraft.value],
      [sceneScopeKey(), () => sceneDraft.value],
      [manuscriptEditScopeKey(), currentManuscriptEdits],
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
    manuscriptProposals,
    activeProposalId,
    manuscriptError,
    manuscriptStatus,
    isCreatingProposal,
    isCreatingProviderProposal,
    isUpdatingProposal,
    manuscriptScenes,
    manuscriptRevisions,
    revisionDiff,
    diffLeftRevisionId,
    diffRightRevisionId,
    isLoadingDiff,
    isRestoringRevision,
    manuscriptExport,
    isExportingManuscript,
    isSavingManuscriptScene,
    editingManuscriptSceneId,
    manuscriptEditTitle,
    manuscriptEditContent,
    manuscriptEditVersion,
    manuscriptEditNeedsReview,
    manuscriptEditReviewReady,
    isRefreshingManuscriptEdit,
    refreshManuscriptEditConflict,
    rebaseManuscriptSceneEdit,
    activeChapter,
    activeSceneContract,
    activeProposal,
    pendingProposalCount,
    unassignedSceneContracts,
    chapterStateLabel,
    sceneStateLabel,
    acceptedSceneCount,
    revisionCount,
    createEmptyChapterDraft,
    createEmptySceneDraft,
    chapterScopeKey,
    sceneScopeKey,
    manuscriptEditScopeKey,
    currentManuscriptEdits,
    loadManuscriptProposals,
    loadManuscriptChapters,
    loadManuscriptScenes,
    loadManuscriptRevisions,
    syncRevisionCompareSelection,
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
    createProposalFromScene,
    updateProposalStatus,
    loadRevisionDiff,
    restoreRevision,
    exportManuscript,
    startEditingManuscriptScene,
    cancelEditingManuscriptScene,
    saveManuscriptSceneEdit,
    revisionLabel,
    resetProjectState,
    draftSnapshotEntries,
  }
})
