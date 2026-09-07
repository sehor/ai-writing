import { defineStore, storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { fetchApi } from '../api/client'
import { readLocation, readPreference, writePreference } from '../services/preferences'
import { useDirtyGuard } from '../composables/useDirtyGuard'
import {
  formatSavedAt,
  isScopeDirty,
  persistDraft,
  restoreCachedDraft,
  restoreEntryDraft,
  setBaseline,
} from '../services/draftSessions'
import { useEditorSessionStore } from './editorSession'
import { useProjectsStore } from './projects'
import { useProjectContextStore } from './projectContext'
import { useSnowflakeStore } from './snowflake'
import { useCanonStore } from './canon'
import { useManuscriptStore } from './manuscript'
import { useMemoryStore } from './memory'
import { useReviewsStore } from './reviews'
import { useGraphStore } from './graph'
import { useNarrativeStore } from './narrative'
import { useProposalDraftStore } from './proposalDraft'
import type {
  WorkflowRuntimeStatus,
  ActiveSection,
  CanonDraft,
  ManuscriptChapterDraft,
  SceneDraft,
  MemoryDraft,
  ReferenceDraft,
  ModelProfile,
} from '../types'

type ApiStatus = 'checking' | 'ok' | 'offline'

/**
 * Application shell: exposes leaf selections for existing components and owns
 * runtime status, navigation guards, project loading and cross-domain wiring.
 * Domain stores read projectContext directly and never import this shell.
 */
export const useWorkspaceStore = defineStore('workspace', () => {
  // ---- Global navigation + runtime status ----
  const context = useProjectContextStore()
  const { activeProjectId, activeStepNumber, selectedModelProfile, projectReload } = storeToRefs(context)
  const { modelExecutionOptions, reloadActiveProject } = context
  const activeSection = ref<ActiveSection>('snowflake')
  const apiStatus = ref<ApiStatus>('checking')
  const workflowRuntime = ref<WorkflowRuntimeStatus | null>(null)
  const modelProfiles = ref<ModelProfile[]>([])

  // ---- Domain stores: coordinated here, never owned here ----
  const editorSession = useEditorSessionStore()
  const projectsStore = useProjectsStore()
  const snowflake = useSnowflakeStore()
  const canon = useCanonStore()
  const manuscript = useManuscriptStore()
  const memory = useMemoryStore()
  const reviews = useReviewsStore()
  const graph = useGraphStore()
  const narrative = useNarrativeStore()
  manuscript.configureReviewPort(reviews)
  reviews.configureRevisionSource(projectId => isActiveProject(projectId) ? manuscript.manuscriptRevisions : [])

  // ---- Draft safety (P0-05): page-close flush + switch guards ----
  const { confirmLeave, confirmLeaveMultiple } = useDirtyGuard({
    flushAll: flushAllDirtyDrafts,
  })

  const runtimeLabel = computed(() => {
    if (!workflowRuntime.value) {
      return '正在检查运行环境'
    }
    if (workflowRuntime.value.runtime_kind === 'model_gateway' || workflowRuntime.value.provider_configured) {
      const provider = workflowRuntime.value.provider || 'Model'
      return `Runtime ${provider} ${workflowRuntime.value.model}`.trim()
    }
    return '本地模式'
  })

  const runtimeTitle = computed(() => workflowRuntime.value?.details || 'Workflow runtime status')

  const activeProject = computed(() =>
    projectsStore.projects.find((project) => project.id === activeProjectId.value) ?? projectsStore.projects[0]
  )

  const activeStep = computed(
    () => snowflake.steps.find((step) => step.number === activeStepNumber.value) ?? snowflake.steps[0]
  )

  function isActiveProject(projectId: string) {
    return projectId === activeProjectId.value
  }

  async function loadInitialData() {
    try {
      const [healthResponse, projectsResponse, stepsResponse, runtimeResponse, profilesResponse] = await Promise.all([
        fetchApi('/health'),
        fetchApi('/projects'),
        fetchApi('/snowflake/steps'),
        fetchApi('/snowflake/workflow/status'),
        fetchApi('/model-profiles'),
      ])
      const health = await healthResponse.json()
      const loadedProjects = await projectsResponse.json()
      const mergedProjects = new Map(
        [...loadedProjects, ...projectsStore.projects].map((project) => [project.id, project])
      )
      projectsStore.projects = [...mergedProjects.values()]
      snowflake.steps = await stepsResponse.json()
      workflowRuntime.value = await runtimeResponse.json()
      modelProfiles.value = await profilesResponse.json()
      if (selectedModelProfile.value && !modelProfiles.value.some((profile) => profile.id === selectedModelProfile.value)) {
        selectedModelProfile.value = ''
      }
      if (!activeProjectId.value) {
        const previousProject = readPreference<string>('project', '')
        activeProjectId.value = projectsStore.projects.find(project => project.id === previousProject)?.id ?? projectsStore.projects[0]?.id ?? ''
      }
      activeStepNumber.value = activeProject.value?.current_step ?? 1
      apiStatus.value = health.status
    } catch {
      apiStatus.value = 'offline'
    }
  }

  /** Set while a save/programmatic change moves a selection itself. */
  let suppressNextSelectionGuard = false

  let projectLoadController: AbortController | null = null
  const isLoadingProject = ref(false)

  watch([activeProjectId, projectReload], async ([projectId, reload], [prevProjectId, previousReload]) => {
    if (reload !== previousReload) flushAllDirtyDrafts()
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else if (prevProjectId && reload === previousReload) {
      // Drafts still hold the outgoing project's values at this point.
      const leaving: Array<[string, string, unknown]> = [
        [useProposalDraftStore().scopeKey, 'AI 草稿', useProposalDraftStore().snapshot()],
        [snowflake.artifactScopeKey(prevProjectId, activeStepNumber.value), 'Snowflake 草稿', snowflake.artifactDraft],
        [canon.canonScopeKey(prevProjectId, canon.activeCanonId), 'Canon 表单', canon.canonDraft],
        [manuscript.chapterScopeKey(prevProjectId, manuscript.activeChapterId), 'Chapter 表单', manuscript.chapterDraft],
        [manuscript.sceneScopeKey(prevProjectId, manuscript.activeSceneId), 'Scene 表单', manuscript.sceneDraft],
        [memory.memoryScopeKey(prevProjectId, memory.activeMemoryId), 'Memory 表单', memory.memoryDraft],
        [manuscript.manuscriptEditScopeKey(prevProjectId, manuscript.editingManuscriptSceneId), '正文编辑', manuscript.currentManuscriptEdits()],
        [reviews.referenceScopeKey(prevProjectId), 'Reference 请求表单', reviews.referenceDraft],
        [narrative.factScopeKey(prevProjectId, narrative.activeFactId), '时态事实表单', narrative.factDraft],
        [narrative.knowledgeScopeKey(prevProjectId, narrative.activeFactId, narrative.activeKnowledgeId), '知识状态表单', narrative.knowledgeDraft],
      ]
      const dirtyScopes = leaving.filter(([key, , value]) => isScopeDirty(key, value))
      if (dirtyScopes.length > 0) {
        if (!confirmLeaveMultiple(dirtyScopes.length)) {
          suppressNextSelectionGuard = true
          activeProjectId.value = prevProjectId
          return
        }
        for (const [key, , value] of dirtyScopes) {
          persistDraft(key, value)
        }
      }
    }
    projectLoadController?.abort()
    const controller = new AbortController()
    projectLoadController = controller
    isLoadingProject.value = !!projectId
    const sectionAtLoadStart = activeSection.value
    if (projectId) writePreference('project', projectId)

    // Tell every domain store to drop the outgoing project's state.
    snowflake.resetProjectState()
    canon.resetProjectState()
    manuscript.resetProjectState()
    memory.resetProjectState()
    reviews.resetProjectState()
    graph.resetProjectState()
    narrative.reset()
    useProposalDraftStore().reset()

    const project = projectsStore.projects.find((item) => item.id === projectId)
    activeStepNumber.value = project?.current_step ?? 1

    if (!projectId) {
      return
    }

    try {
      const [
        artifactResponse,
        snowflakeStepStateResponse,
        snowflakeRevisionResponse,
        canonResponse,
        chapterResponse,
        sceneResponse,
        memoryResponse,
        proposalResponse,
        manuscriptSceneResponse,
        manuscriptRevisionResponse,
        writebackResponse,
        referenceResponse,
        ] =
          await Promise.all([
            fetchApi(`/projects/${projectId}/snowflake/artifacts`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/snowflake/steps`, {
              signal: controller.signal,
            }),
            fetchApi(
              `/projects/${projectId}/snowflake/artifacts/${activeStepNumber.value}/revisions?page=1&page_size=100`,
              { signal: controller.signal }
            ),
            fetchApi(`/projects/${projectId}/canon/entities`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/manuscript/chapters`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/scene-contracts`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/memory/records`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/manuscript/proposals`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/manuscript/scenes`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/manuscript/revisions`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/writeback/proposals`, {
              signal: controller.signal,
            }),
            fetchApi(`/projects/${projectId}/references/suggestions`, {
              signal: controller.signal,
            }),
          ])
      if (
        !artifactResponse.ok ||
        !snowflakeStepStateResponse.ok ||
        !snowflakeRevisionResponse.ok ||
        !canonResponse.ok ||
        !chapterResponse.ok ||
        !sceneResponse.ok ||
        !memoryResponse.ok ||
        !proposalResponse.ok ||
        !manuscriptSceneResponse.ok ||
        !manuscriptRevisionResponse.ok ||
        !writebackResponse.ok ||
        !referenceResponse.ok
      ) {
        throw new Error('Could not load artifacts')
      }
      const [
        loadedArtifacts,
        loadedSnowflakeStepStates,
        loadedSnowflakeRevisionPage,
        loadedCanonEntities,
        loadedChapters,
        loadedSceneContracts,
        loadedMemoryRecords,
        loadedProposals,
        loadedManuscriptScenes,
        loadedRevisions,
        loadedWritebacks,
        loadedReferences,
      ] = await Promise.all([
        artifactResponse.json(),
        snowflakeStepStateResponse.json(),
        snowflakeRevisionResponse.json(),
        canonResponse.json(),
        chapterResponse.json(),
        sceneResponse.json(),
        memoryResponse.json(),
        proposalResponse.json(),
        manuscriptSceneResponse.json(),
        manuscriptRevisionResponse.json(),
        writebackResponse.json(),
        referenceResponse.json(),
      ])
      if (controller.signal.aborted) {
        return
      }
      snowflake.artifacts = loadedArtifacts
      snowflake.stepStates = loadedSnowflakeStepStates
      snowflake.revisions = loadedSnowflakeRevisionPage.data
      canon.canonEntities = loadedCanonEntities
      manuscript.manuscriptChapters = loadedChapters
      manuscript.sceneContracts = loadedSceneContracts
      memory.memoryRecords = loadedMemoryRecords
      manuscript.manuscriptProposals = loadedProposals
      manuscript.manuscriptScenes = loadedManuscriptScenes
      manuscript.manuscriptRevisions = loadedRevisions
      reviews.writebackProposals = loadedWritebacks
      reviews.referenceSuggestions = loadedReferences
      manuscript.activeProposalId = manuscript.manuscriptProposals[0]?.id ?? ''
      const location = readLocation(projectId)
      if (activeSection.value === sectionAtLoadStart) {
        activeSection.value = location?.section ?? (loadedManuscriptScenes.length ? 'manuscript' : 'snowflake')
      }
      manuscript.activeChapterId = loadedChapters.some((chapter: { id: string }) => chapter.id === location?.chapter)
        ? location!.chapter : loadedChapters[0]?.id ?? ''
      manuscript.activeSceneId = loadedSceneContracts.some((scene: { id: string }) => scene.id === location?.scene)
        ? location!.scene : loadedManuscriptScenes[0]?.scene_id ?? loadedSceneContracts[0]?.id ?? ''
      reviews.activeWritebackId = reviews.writebackProposals[0]?.id ?? ''
      reviews.activeReferenceId = reviews.referenceSuggestions[0]?.id ?? ''
      manuscript.syncRevisionCompareSelection()
      // Entry-time draft restore for the incoming project.
      const incomingArtifactScope = snowflake.artifactScopeKey(projectId, activeStepNumber.value)
      const baselineContent = snowflake.activeStepState?.accepted_revision?.content ?? ''
      setBaseline(incomingArtifactScope, baselineContent)
      snowflake.artifactDraft = baselineContent
      const cachedArtifact = restoreCachedDraft<string>(incomingArtifactScope)
      if (cachedArtifact && typeof cachedArtifact.value === 'string') {
        snowflake.artifactDraft = cachedArtifact.value
        editorSession.markDirty(incomingArtifactScope, cachedArtifact.savedAt)
        snowflake.artifactStatus = `已恢复本地草稿（自动保存于 ${formatSavedAt(cachedArtifact.savedAt)}）`
      }
      restoreEntryDraft<CanonDraft>(canon.canonScopeKey(), canon.createEmptyCanonDraft(), (cached) => {
        canon.canonDraft = cached
      }, (message) => {
        canon.canonStatus = message
      })
      restoreEntryDraft<ManuscriptChapterDraft>(manuscript.chapterScopeKey(), manuscript.createEmptyChapterDraft(), (cached) => {
        manuscript.chapterDraft = cached
      }, (message) => {
        manuscript.chapterStatus = message
      })
      restoreEntryDraft<SceneDraft>(manuscript.sceneScopeKey(), manuscript.createEmptySceneDraft(), (cached) => {
        manuscript.sceneDraft = cached
      }, (message) => {
        manuscript.sceneStatus = message
      })
      restoreEntryDraft<MemoryDraft>(memory.memoryScopeKey(), memory.createEmptyMemoryDraft(), (cached) => {
        memory.memoryDraft = cached
      }, (message) => {
        memory.memoryStatus = message
      })
      restoreEntryDraft<ReferenceDraft>(reviews.referenceScopeKey(), reviews.createEmptyReferenceDraft(), (cached) => {
        reviews.referenceDraft = cached
      }, (message) => {
        reviews.referenceStatus = message
      })
      await Promise.all([
        graph.loadGraphAnalysis(projectId, controller.signal),
        snowflake.loadManuscriptProgress(projectId),
        reviews.loadPostAcceptAnalysisJobs(projectId),
        narrative.load(projectId),
      ])
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      snowflake.artifactError = '项目数据加载失败，请重试。'
    } finally {
      if (!controller.signal.aborted) isLoadingProject.value = false
    }
  })

  watch([activeSection, () => manuscript.activeChapterId, () => manuscript.activeSceneId], () => {
    if (activeProjectId.value && !isLoadingProject.value) writePreference(`location:${activeProjectId.value}`, {
      section: activeSection.value, chapter: manuscript.activeChapterId, scene: manuscript.activeSceneId,
    })
  }, { flush: 'post' })

  watch(activeStepNumber, (next, prev) => {
    if (suppressNextSelectionGuard) {
      suppressNextSelectionGuard = false
    } else {
      const previousScope = snowflake.artifactScopeKey(activeProjectId.value, prev)
      if (isScopeDirty(previousScope, snowflake.artifactDraft)) {
        if (!confirmLeave(previousScope, `Snowflake Step ${prev}`)) {
          suppressNextSelectionGuard = true
          activeStepNumber.value = prev
          return
        }
        persistDraft(previousScope, snowflake.artifactDraft)
      }
    }
    snowflake.artifactError = ''
    snowflake.artifactStatus = ''
    snowflake.workflowTrace = []
    const nextScope = snowflake.artifactScopeKey()
    snowflake.revisions = []
    snowflake.activeRevisionId = ''
    void snowflake.loadRevisions(next).catch(() => {
      snowflake.artifactError = 'Revision history could not be loaded.'
    })
    const baselineContent = snowflake.activeStepState?.accepted_revision?.content ?? ''
    setBaseline(nextScope, baselineContent)
    const cached = restoreCachedDraft<string>(nextScope)
    if (cached && typeof cached.value === 'string') {
      snowflake.artifactDraft = cached.value
      editorSession.markDirty(nextScope, cached.savedAt)
      snowflake.artifactStatus = `已恢复本地草稿（自动保存于 ${formatSavedAt(cached.savedAt)}）`
    } else {
      snowflake.artifactDraft = baselineContent
    }
  })

  /** Flush every dirty domain draft into the local cache (page-close safety). */
  function flushAllDirtyDrafts(): void {
    useProposalDraftStore().persist()
    const snapshots: Array<[string, () => unknown]> = [
      ...snowflake.draftSnapshotEntries(),
      ...canon.draftSnapshotEntries(),
      ...manuscript.draftSnapshotEntries(),
      ...memory.draftSnapshotEntries(),
      ...reviews.draftSnapshotEntries(),
      ...narrative.draftSnapshotEntries(),
    ]
    for (const [scopeKey, read] of snapshots) {
      const value = read()
      if (isScopeDirty(scopeKey, value)) {
        persistDraft(scopeKey, value)
      }
    }
  }

  function selectStep(stepNumber: number) {
    activeStepNumber.value = stepNumber
  }


  return {
    reloadActiveProject,
    isLoadingProject,
    activeProjectId,
    activeSection,
    activeStepNumber,
    apiStatus,
    workflowRuntime,
    modelProfiles,
    selectedModelProfile,
    runtimeLabel,
    runtimeTitle,
    activeProject,
    activeStep,
    isActiveProject,
    selectStep,
    modelExecutionOptions,
    loadInitialData,
    flushAllDirtyDrafts,
  }
})
