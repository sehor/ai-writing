import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type {
  ProjectSummary,
  SnowflakeStep,
  SnowflakeArtifact,
  WorkflowAgentTrace,
  SnowflakeGenerationResponse,
  CanonEntity,
  CanonDraft,
  SceneContract,
  SceneDraft,
  ManuscriptChapter,
  ManuscriptChapterDraft,
  MemoryRecord,
  MemoryDraft,
  ChapterCompileResponse,
  ManuscriptProposalStatus,
  ManuscriptProposal,
  ManuscriptScene,
  ManuscriptRevision,
  ManuscriptRevisionDiff,
  ManuscriptExport,
  WritebackProposalStatus,
  ReferenceSuggestionStatus,
  WritebackProposal,
  ReferenceSuggestion,
  ReferenceDraft,
  HermesRevisionProcessResponse,
  GraphAnalysisResponse,
  WorkflowRuntimeStatus,
  ActiveSection
} from "../types"

type ApiStatus = 'checking' | 'ok' | 'offline'

export const useWorkspaceStore = defineStore('workspace', () => {
  const projects = ref<ProjectSummary[]>([])
  const steps = ref<SnowflakeStep[]>([])
  const artifacts = ref<SnowflakeArtifact[]>([])
  const canonEntities = ref<CanonEntity[]>([])
  const sceneContracts = ref<SceneContract[]>([])
  const manuscriptChapters = ref<ManuscriptChapter[]>([])
  const memoryRecords = ref<MemoryRecord[]>([])
  const manuscriptProposals = ref<ManuscriptProposal[]>([])
  const manuscriptScenes = ref<ManuscriptScene[]>([])
  const manuscriptRevisions = ref<ManuscriptRevision[]>([])
  const writebackProposals = ref<WritebackProposal[]>([])
  const referenceSuggestions = ref<ReferenceSuggestion[]>([])
  const hermesProcessReport = ref<HermesRevisionProcessResponse | null>(null)
  const activeProjectId = ref('')
  const activeStepNumber = ref(1)
  const activeSection = ref<ActiveSection>('snowflake')
  const activeCanonId = ref('')
  const activeChapterId = ref('')
  const activeSceneId = ref('')
  const activeMemoryId = ref('')
  const activeProposalId = ref('')
  const activeWritebackId = ref('')
  const activeReferenceId = ref('')
  const diffLeftRevisionId = ref('')
  const diffRightRevisionId = ref('')
  const editingManuscriptSceneId = ref('')
  const apiStatus = ref<ApiStatus>('checking')
  const workflowRuntime = ref<WorkflowRuntimeStatus | null>(null)
  const isCreating = ref(false)
  const isSavingArtifact = ref(false)
  const isGeneratingArtifact = ref(false)
  const isSavingCanon = ref(false)
  const isDeletingCanon = ref(false)
  const isSavingScene = ref(false)
  const isDeletingScene = ref(false)
  const isSavingChapter = ref(false)
  const isDeletingChapter = ref(false)
  const isCompilingScene = ref(false)
  const isSavingMemory = ref(false)
  const isDeletingMemory = ref(false)
  const isLoadingGraph = ref(false)
  const isCreatingProposal = ref(false)
  const isCreatingProviderProposal = ref(false)
  const isUpdatingProposal = ref(false)
  const isSavingManuscriptScene = ref(false)
  const isExportingManuscript = ref(false)
  const isLoadingDiff = ref(false)
  const isRestoringRevision = ref(false)
  const isCreatingWriteback = ref(false)
  const isCreatingProviderWriteback = ref(false)
  const isProcessingHermesRevision = ref(false)
  const isUpdatingWriteback = ref(false)
  const isGeneratingReference = ref(false)
  const isGeneratingProviderReference = ref(false)
  const isUpdatingReference = ref(false)
  const createError = ref('')
  const artifactError = ref('')
  const artifactStatus = ref('')
  const canonError = ref('')
  const canonStatus = ref('')
  const chapterError = ref('')
  const chapterStatus = ref('')
  const sceneError = ref('')
  const sceneStatus = ref('')
  const memoryError = ref('')
  const memoryStatus = ref('')
  const graphError = ref('')
  const manuscriptError = ref('')
  const manuscriptStatus = ref('')
  const writebackError = ref('')
  const writebackStatus = ref('')
  const referenceError = ref('')
  const referenceStatus = ref('')
  const artifactDraft = ref('')
  const workflowTrace = ref<WorkflowAgentTrace[]>([])
  const manuscriptEditTitle = ref('')
  const manuscriptEditContent = ref('')
  const canonDraft = ref<CanonDraft>(createEmptyCanonDraft())
  const sceneDraft = ref<SceneDraft>(createEmptySceneDraft())
  const chapterDraft = ref<ManuscriptChapterDraft>(createEmptyChapterDraft())
  const memoryDraft = ref<MemoryDraft>(createEmptyMemoryDraft())
  const referenceDraft = ref<ReferenceDraft>(createEmptyReferenceDraft())
  const compileResult = ref<ChapterCompileResponse | null>(null)
  const graphAnalysis = ref<GraphAnalysisResponse | null>(null)
  const revisionDiff = ref<ManuscriptRevisionDiff | null>(null)
  const manuscriptExport = ref<ManuscriptExport | null>(null)
  const newProject = ref({
    title: '',
    premise: '',
  })
  
  const runtimeLabel = computed(() => {
    if (!workflowRuntime.value) {
      return 'Runtime checking'
    }
    if (workflowRuntime.value.runtime === 'provider_deepseek') {
      return `Runtime DeepSeek ${workflowRuntime.value.model}`
    }
    return 'Runtime Local'
  })
  
  const runtimeTitle = computed(() => workflowRuntime.value?.details || 'Workflow runtime status')
  
  const activeProject = computed(() =>
    projects.value.find((project) => project.id === activeProjectId.value) ?? projects.value[0]
  )
  
  const activeStep = computed(
    () => steps.value.find((step) => step.number === activeStepNumber.value) ?? steps.value[0]
  )
  
  const savedActiveArtifact = computed(() =>
    artifacts.value.find((artifact) => artifact.step_number === activeStepNumber.value)
  )
  
  const activeCanonEntity = computed(() =>
    canonEntities.value.find((entity) => entity.id === activeCanonId.value)
  )
  
  const activeChapter = computed(() =>
    manuscriptChapters.value.find((chapter) => chapter.id === activeChapterId.value)
  )
  
  const activeSceneContract = computed(() =>
    sceneContracts.value.find((scene) => scene.id === activeSceneId.value)
  )
  
  const activeMemoryRecord = computed(() =>
    memoryRecords.value.find((record) => record.id === activeMemoryId.value)
  )
  
  const activeProposal = computed(() =>
    manuscriptProposals.value.find((proposal) => proposal.id === activeProposalId.value)
  )
  
  const activeWritebackProposal = computed(() =>
    writebackProposals.value.find((proposal) => proposal.id === activeWritebackId.value)
  )
  
  const activeReferenceSuggestion = computed(() =>
    referenceSuggestions.value.find((suggestion) => suggestion.id === activeReferenceId.value)
  )
  
  const pendingProposalCount = computed(
    () => manuscriptProposals.value.filter((proposal) => proposal.status === 'pending_review').length
  )
  
  const pendingWritebackCount = computed(
    () => writebackProposals.value.filter((proposal) => proposal.status === 'pending_review').length
  )
  
  const pendingReferenceCount = computed(
    () => referenceSuggestions.value.filter((suggestion) => suggestion.status === 'pending_review').length
  )
  
  const acceptedSceneCount = computed(() => manuscriptScenes.value.length)
  
  const revisionCount = computed(() => manuscriptRevisions.value.length)
  
  const unassignedSceneContracts = computed(() =>
    sceneContracts.value.filter((scene) => !scene.chapter_id)
  )
  
  const hasUnsavedArtifactChanges = computed(
    () => artifactDraft.value.trim() !== (savedActiveArtifact.value?.content ?? '')
  )
  
  const artifactStateLabel = computed(() => {
    if (artifactStatus.value) {
      return artifactStatus.value
    }
    if (hasUnsavedArtifactChanges.value) {
      return 'Unsaved changes'
    }
    return savedActiveArtifact.value ? 'Saved state loaded' : 'No saved artifact yet'
  })
  
  const canonStateLabel = computed(() => {
    if (canonStatus.value) {
      return canonStatus.value
    }
    return activeCanonEntity.value ? 'Editing Canon entity' : 'New Canon entity'
  })
  
  const sceneStateLabel = computed(() => {
    if (sceneStatus.value) {
      return sceneStatus.value
    }
    return activeSceneContract.value ? 'Editing Scene contract' : 'New Scene contract'
  })
  
  const chapterStateLabel = computed(() => {
    if (chapterStatus.value) {
      return chapterStatus.value
    }
    return activeChapter.value ? 'Editing Chapter' : 'New Chapter'
  })
  
  const memoryStateLabel = computed(() => {
    if (memoryStatus.value) {
      return memoryStatus.value
    }
    return activeMemoryRecord.value ? 'Editing Memory / Style record' : 'New Memory / Style record'
  })
  
  function createEmptyCanonDraft(): CanonDraft {
    return {
      entity_type: 'character',
      name: '',
      summary: '',
      current_state: '',
      constraints: '',
      last_seen: '',
      timeline_notes: '',
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
  
  function createEmptyChapterDraft(): ManuscriptChapterDraft {
    return {
      sequence: 1,
      title: '',
      summary: '',
    }
  }
  
  function createEmptyMemoryDraft(): MemoryDraft {
    return {
      record_type: 'chapter_summary',
      title: '',
      scope: '',
      content: '',
      tags: '',
      source_ref: '',
    }
  }
  
  function createEmptyReferenceDraft(): ReferenceDraft {
    return {
      suggestion_type: 'scene_bridge',
      scope_type: 'scene',
      scope_ref: '',
      author_problem: '',
      desired_output: '',
    }
  }
  
  async function loadInitialData() {
    try {
      const [healthResponse, projectsResponse, stepsResponse, runtimeResponse] = await Promise.all([
        fetch('/api/health'),
        fetch('/api/projects'),
        fetch('/api/snowflake/steps'),
        fetch('/api/snowflake/workflow/status'),
      ])
      const health = await healthResponse.json()
      projects.value = await projectsResponse.json()
      steps.value = await stepsResponse.json()
      workflowRuntime.value = await runtimeResponse.json()
      activeProjectId.value = projects.value[0]?.id ?? ''
      activeStepNumber.value = activeProject.value?.current_step ?? 1
      apiStatus.value = health.status
    } catch {
      apiStatus.value = 'offline'
    }
  }
  
  let projectLoadController: AbortController | null = null

  watch(activeProjectId, async (projectId) => {
    projectLoadController?.abort()
    const controller = new AbortController()
    projectLoadController = controller
    artifactError.value = ''
    artifactStatus.value = ''
    workflowTrace.value = []
    canonError.value = ''
    canonStatus.value = ''
    chapterError.value = ''
    chapterStatus.value = ''
    sceneError.value = ''
    sceneStatus.value = ''
    memoryError.value = ''
    memoryStatus.value = ''
    graphError.value = ''
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    writebackError.value = ''
    writebackStatus.value = ''
    referenceError.value = ''
    referenceStatus.value = ''
    artifacts.value = []
    canonEntities.value = []
    manuscriptChapters.value = []
    sceneContracts.value = []
    memoryRecords.value = []
    manuscriptProposals.value = []
    manuscriptScenes.value = []
    manuscriptRevisions.value = []
    writebackProposals.value = []
    referenceSuggestions.value = []
    hermesProcessReport.value = null
    graphAnalysis.value = null
    revisionDiff.value = null
    manuscriptExport.value = null
    compileResult.value = null
    artifactDraft.value = ''
    activeCanonId.value = ''
    activeChapterId.value = ''
    activeSceneId.value = ''
    activeMemoryId.value = ''
    activeProposalId.value = ''
    activeWritebackId.value = ''
    activeReferenceId.value = ''
    diffLeftRevisionId.value = ''
    diffRightRevisionId.value = ''
    editingManuscriptSceneId.value = ''
    manuscriptEditTitle.value = ''
    manuscriptEditContent.value = ''
    canonDraft.value = createEmptyCanonDraft()
    chapterDraft.value = createEmptyChapterDraft()
    sceneDraft.value = createEmptySceneDraft()
    memoryDraft.value = createEmptyMemoryDraft()
    referenceDraft.value = createEmptyReferenceDraft()
  
    const project = projects.value.find((item) => item.id === projectId)
    activeStepNumber.value = project?.current_step ?? 1
  
    if (!projectId) {
      return
    }
  
    try {
      const [
        artifactResponse,
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
            fetch(`/api/projects/${projectId}/snowflake/artifacts`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/canon/entities`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/manuscript/chapters`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/scene-contracts`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/memory/records`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/manuscript/proposals`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/manuscript/scenes`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/manuscript/revisions`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/writeback/proposals`, {
              signal: controller.signal,
            }),
            fetch(`/api/projects/${projectId}/references/suggestions`, {
              signal: controller.signal,
            }),
          ])
      if (
        !artifactResponse.ok ||
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
      artifacts.value = loadedArtifacts
      canonEntities.value = loadedCanonEntities
      manuscriptChapters.value = loadedChapters
      sceneContracts.value = loadedSceneContracts
      memoryRecords.value = loadedMemoryRecords
      manuscriptProposals.value = loadedProposals
      manuscriptScenes.value = loadedManuscriptScenes
      manuscriptRevisions.value = loadedRevisions
      writebackProposals.value = loadedWritebacks
      referenceSuggestions.value = loadedReferences
      activeProposalId.value = manuscriptProposals.value[0]?.id ?? ''
      activeWritebackId.value = writebackProposals.value[0]?.id ?? ''
      activeReferenceId.value = referenceSuggestions.value[0]?.id ?? ''
      syncRevisionCompareSelection()
      artifactDraft.value = savedActiveArtifact.value?.content ?? ''
      await loadGraphAnalysis(projectId, controller.signal)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      artifactError.value = 'Project data could not be loaded.'
    }
  })
  
  watch(activeStepNumber, () => {
    artifactError.value = ''
    artifactStatus.value = ''
    workflowTrace.value = []
    artifactDraft.value = savedActiveArtifact.value?.content ?? ''
  })
  
  watch(activeCanonId, () => {
    canonError.value = ''
    canonStatus.value = ''
    const selected = activeCanonEntity.value
    canonDraft.value = selected
      ? {
          entity_type: selected.entity_type,
          name: selected.name,
          summary: selected.summary,
          current_state: selected.current_state,
          constraints: selected.constraints,
          last_seen: selected.last_seen,
          timeline_notes: selected.timeline_notes,
        }
      : createEmptyCanonDraft()
  })
  
  watch(activeChapterId, () => {
    chapterError.value = ''
    chapterStatus.value = ''
    const selected = activeChapter.value
    chapterDraft.value = selected
      ? {
          sequence: selected.sequence,
          title: selected.title,
          summary: selected.summary,
        }
      : createEmptyChapterDraft()
  })
  
  watch(activeSceneId, () => {
    sceneError.value = ''
    sceneStatus.value = ''
    compileResult.value = null
    const selected = activeSceneContract.value
    sceneDraft.value = selected
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
  })
  
  watch(activeMemoryId, () => {
    memoryError.value = ''
    memoryStatus.value = ''
    const selected = activeMemoryRecord.value
    memoryDraft.value = selected
      ? {
          record_type: selected.record_type,
          title: selected.title,
          scope: selected.scope,
          content: selected.content,
          tags: selected.tags,
          source_ref: selected.source_ref,
        }
      : createEmptyMemoryDraft()
  })
  
  async function createProject() {
    createError.value = ''
    const title = newProject.value.title.trim()
    const premise = newProject.value.premise.trim()
    if (!title || !premise) {
      createError.value = 'Title and premise are required.'
      return
    }
  
    isCreating.value = true
    try {
      const response = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, premise }),
      })
      if (!response.ok) {
        throw new Error('Could not create project')
      }
      const created = await response.json()
      projects.value = [...projects.value, created]
      activeProjectId.value = created.id
      newProject.value = { title: '', premise: '' }
    } catch {
      createError.value = 'Project creation failed. Check that the API is running.'
    } finally {
      isCreating.value = false
    }
  }
  
  function selectStep(stepNumber: number) {
    activeStepNumber.value = stepNumber
  }
  
  function upsertArtifact(artifact: SnowflakeArtifact) {
    artifacts.value = [
      ...artifacts.value.filter((item) => item.step_number !== artifact.step_number),
      artifact,
    ].sort((left, right) => left.step_number - right.step_number)
  }
  
  function advanceActiveProject(completedStep: number) {
    const project = activeProject.value
    if (!project) {
      return
    }
    const nextStep = Math.min(completedStep + 1, 10)
    projects.value = projects.value.map((item) =>
      item.id === project.id
        ? { ...item, current_step: Math.max(item.current_step, nextStep) }
      : item
    )
  }
  
  async function loadGraphAnalysis(
    projectId = activeProject.value?.id,
    signal?: AbortSignal,
  ) {
    graphError.value = ''
    if (!projectId) {
      graphAnalysis.value = null
      return
    }
  
    isLoadingGraph.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/graph/analysis`, { signal })
      if (!response.ok) {
        throw new Error('Could not load graph analysis')
      }
      graphAnalysis.value = await response.json()
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      graphError.value = 'Graph analysis could not be loaded.'
    } finally {
      if (!signal?.aborted) {
        isLoadingGraph.value = false
      }
    }
  }
  
  async function loadManuscriptProposals(projectId = activeProject.value?.id) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptProposals.value = []
      activeProposalId.value = ''
      return
    }
  
    try {
      const response = await fetch(`/api/projects/${projectId}/manuscript/proposals`)
      if (!response.ok) {
        throw new Error('Could not load manuscript proposals')
      }
      manuscriptProposals.value = await response.json()
      if (!manuscriptProposals.value.some((proposal) => proposal.id === activeProposalId.value)) {
        activeProposalId.value = manuscriptProposals.value[0]?.id ?? ''
      }
    } catch {
      manuscriptError.value = 'Manuscript proposals could not be loaded.'
    }
  }
  
  async function loadManuscriptChapters(projectId = activeProject.value?.id) {
    chapterError.value = ''
    if (!projectId) {
      manuscriptChapters.value = []
      activeChapterId.value = ''
      return
    }
  
    try {
      const response = await fetch(`/api/projects/${projectId}/manuscript/chapters`)
      if (!response.ok) {
        throw new Error('Could not load manuscript chapters')
      }
      manuscriptChapters.value = await response.json()
      if (!manuscriptChapters.value.some((chapter) => chapter.id === activeChapterId.value)) {
        activeChapterId.value = manuscriptChapters.value[0]?.id ?? ''
      }
    } catch {
      chapterError.value = 'Manuscript chapters could not be loaded.'
    }
  }
  
  async function loadManuscriptScenes(projectId = activeProject.value?.id) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptScenes.value = []
      return
    }
  
    try {
      const response = await fetch(`/api/projects/${projectId}/manuscript/scenes`)
      if (!response.ok) {
        throw new Error('Could not load manuscript scenes')
      }
      manuscriptScenes.value = await response.json()
    } catch {
      manuscriptError.value = 'Accepted manuscript scenes could not be loaded.'
    }
  }
  
  async function loadManuscriptRevisions(projectId = activeProject.value?.id) {
    manuscriptError.value = ''
    if (!projectId) {
      manuscriptRevisions.value = []
      revisionDiff.value = null
      diffLeftRevisionId.value = ''
      diffRightRevisionId.value = ''
      return
    }
  
    try {
      const response = await fetch(`/api/projects/${projectId}/manuscript/revisions`)
      if (!response.ok) {
        throw new Error('Could not load manuscript revisions')
      }
      manuscriptRevisions.value = await response.json()
      syncRevisionCompareSelection()
    } catch {
      manuscriptError.value = 'Manuscript revision history could not be loaded.'
    }
  }
  
  async function loadWritebackProposals(projectId = activeProject.value?.id) {
    writebackError.value = ''
    if (!projectId) {
      writebackProposals.value = []
      activeWritebackId.value = ''
      return
    }
  
    try {
      const response = await fetch(`/api/projects/${projectId}/writeback/proposals`)
      if (!response.ok) {
        throw new Error('Could not load write-back proposals')
      }
      writebackProposals.value = await response.json()
      if (!writebackProposals.value.some((proposal) => proposal.id === activeWritebackId.value)) {
        activeWritebackId.value = writebackProposals.value[0]?.id ?? ''
      }
    } catch {
      writebackError.value = 'Write-back proposals could not be loaded.'
    }
  }
  
  async function loadReferenceSuggestions(projectId = activeProject.value?.id) {
    referenceError.value = ''
    if (!projectId) {
      referenceSuggestions.value = []
      activeReferenceId.value = ''
      return
    }
  
    try {
      const response = await fetch(`/api/projects/${projectId}/references/suggestions`)
      if (!response.ok) {
        throw new Error('Could not load reference suggestions')
      }
      referenceSuggestions.value = await response.json()
      if (!referenceSuggestions.value.some((suggestion) => suggestion.id === activeReferenceId.value)) {
        activeReferenceId.value = referenceSuggestions.value[0]?.id ?? ''
      }
    } catch {
      referenceError.value = 'Reference suggestions could not be loaded.'
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
  
  function startNewCanonEntity() {
    activeCanonId.value = ''
    canonDraft.value = createEmptyCanonDraft()
    canonStatus.value = ''
    canonError.value = ''
  }
  
  function startNewChapter() {
    activeChapterId.value = ''
    chapterDraft.value = {
      ...createEmptyChapterDraft(),
      sequence: manuscriptChapters.value.length + 1,
    }
    chapterStatus.value = ''
    chapterError.value = ''
  }
  
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
  
  function startNewMemoryRecord() {
    activeMemoryId.value = ''
    memoryDraft.value = createEmptyMemoryDraft()
    memoryStatus.value = ''
    memoryError.value = ''
  }
  
  async function saveArtifact() {
    artifactError.value = ''
    artifactStatus.value = ''
    const projectId = activeProject.value?.id
    const content = artifactDraft.value.trim()
  
    if (!projectId || !activeStep.value) {
      artifactError.value = 'Create or select a project first.'
      return
    }
  
    if (!content) {
      artifactError.value = 'Artifact content is required before saving.'
      return
    }
  
    isSavingArtifact.value = true
    try {
      const response = await fetch(
        `/api/projects/${projectId}/snowflake/artifacts/${activeStepNumber.value}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
        }
      )
      if (!response.ok) {
        throw new Error('Could not save artifact')
      }
      const saved = await response.json()
      upsertArtifact(saved)
      advanceActiveProject(saved.step_number)
      artifactDraft.value = saved.content
      artifactStatus.value = 'Artifact saved.'
      await loadGraphAnalysis(projectId)
    } catch {
      artifactError.value = 'Artifact save failed. Check that the API is running.'
    } finally {
      isSavingArtifact.value = false
    }
  }
  
  async function generateArtifact() {
    artifactError.value = ''
    artifactStatus.value = ''
    workflowTrace.value = []
    const projectId = activeProject.value?.id
    const userInput = artifactDraft.value.trim() || activeProject.value?.premise.trim()
  
    if (!projectId || !activeStep.value || !userInput) {
      artifactError.value = 'Create or select a project first.'
      return
    }
  
    isGeneratingArtifact.value = true
    try {
      const response = await fetch('/api/snowflake/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          step_number: activeStepNumber.value,
          user_input: userInput,
        }),
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        if (detail.workflow_trace) {
          workflowTrace.value = detail.workflow_trace
        }
        throw new Error(detail.message || 'Could not generate artifact')
      }
      const generated: SnowflakeGenerationResponse = await response.json()
      upsertArtifact(generated)
      advanceActiveProject(generated.step_number)
      artifactDraft.value = generated.content
      workflowTrace.value = generated.workflow_trace
      artifactStatus.value = 'Draft generated and saved.'
      await loadGraphAnalysis(projectId)
    } catch (error) {
      artifactError.value =
        error instanceof Error
          ? `Draft generation failed. ${error.message}`
          : 'Draft generation failed. Check that the API is running.'
    } finally {
      isGeneratingArtifact.value = false
    }
  }
  
  async function readErrorDetail(response: Response): Promise<{
    message?: string
    workflow_trace?: WorkflowAgentTrace[]
  }> {
    try {
      const payload = await response.json()
      if (typeof payload.detail === 'string') {
        return { message: payload.detail }
      }
      return payload.detail ?? {}
    } catch {
      return {}
    }
  }
  
  async function saveCanonEntity() {
    canonError.value = ''
    canonStatus.value = ''
    const projectId = activeProject.value?.id
    const name = canonDraft.value.name.trim()
  
    if (!projectId) {
      canonError.value = 'Create or select a project first.'
      return
    }
  
    if (!name) {
      canonError.value = 'Canon entity name is required.'
      return
    }
  
    isSavingCanon.value = true
    try {
      const body = JSON.stringify({
        ...canonDraft.value,
        name,
        summary: canonDraft.value.summary.trim(),
        current_state: canonDraft.value.current_state.trim(),
        constraints: canonDraft.value.constraints.trim(),
        last_seen: canonDraft.value.last_seen.trim(),
        timeline_notes: canonDraft.value.timeline_notes.trim(),
      })
      const url = activeCanonId.value
        ? `/api/projects/${projectId}/canon/entities/${activeCanonId.value}`
        : `/api/projects/${projectId}/canon/entities`
      const response = await fetch(url, {
        method: activeCanonId.value ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Canon entity')
      }
      const saved = await response.json()
      canonEntities.value = [
        ...canonEntities.value.filter((entity) => entity.id !== saved.id),
        saved,
      ].sort((left, right) =>
        `${left.entity_type}:${left.name}`.localeCompare(`${right.entity_type}:${right.name}`)
      )
      activeCanonId.value = saved.id
      canonStatus.value = 'Canon entity saved.'
      await loadGraphAnalysis(projectId)
    } catch {
      canonError.value = 'Canon save failed. Check for duplicate names or API errors.'
    } finally {
      isSavingCanon.value = false
    }
  }
  
  async function deleteCanonEntity() {
    canonError.value = ''
    canonStatus.value = ''
    const projectId = activeProject.value?.id
    const entityId = activeCanonId.value
  
    if (!projectId || !entityId) {
      canonError.value = 'Select a Canon entity first.'
      return
    }
  
    isDeletingCanon.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/canon/entities/${entityId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Canon entity')
      }
      canonEntities.value = canonEntities.value.filter((entity) => entity.id !== entityId)
      startNewCanonEntity()
      canonStatus.value = 'Canon entity deleted.'
      await loadGraphAnalysis(projectId)
    } catch {
      canonError.value = 'Canon delete failed. Check that the API is running.'
    } finally {
      isDeletingCanon.value = false
    }
  }
  
  async function saveChapter() {
    chapterError.value = ''
    chapterStatus.value = ''
    const projectId = activeProject.value?.id
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
        ? `/api/projects/${projectId}/manuscript/chapters/${activeChapterId.value}`
        : `/api/projects/${projectId}/manuscript/chapters`
      const response = await fetch(url, {
        method: activeChapterId.value ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Chapter')
      }
      const saved: ManuscriptChapter = await response.json()
      manuscriptChapters.value = [
        ...manuscriptChapters.value.filter((chapter) => chapter.id !== saved.id),
        saved,
      ].sort((left, right) => left.sequence - right.sequence)
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
    const projectId = activeProject.value?.id
    const chapterId = activeChapterId.value
  
    if (!projectId || !chapterId) {
      chapterError.value = 'Select a Chapter first.'
      return
    }
  
    isDeletingChapter.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/manuscript/chapters/${chapterId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Chapter')
      }
      manuscriptChapters.value = manuscriptChapters.value.filter((chapter) => chapter.id !== chapterId)
      sceneContracts.value = sceneContracts.value.map((scene) =>
        scene.chapter_id === chapterId ? { ...scene, chapter_id: '' } : scene
      )
      startNewChapter()
      chapterStatus.value = 'Chapter deleted. Its scenes are now unassigned.'
      await loadGraphAnalysis(projectId)
    } catch {
      chapterError.value = 'Chapter delete failed. Check that the API is running.'
    } finally {
      isDeletingChapter.value = false
    }
  }
  
  async function saveSceneContract() {
    sceneError.value = ''
    sceneStatus.value = ''
    const projectId = activeProject.value?.id
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
        ? `/api/projects/${projectId}/scene-contracts/${activeSceneId.value}`
        : `/api/projects/${projectId}/scene-contracts`
      const response = await fetch(url, {
        method: activeSceneId.value ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Scene contract')
      }
      const saved = await response.json()
      sceneContracts.value = [
        ...sceneContracts.value.filter((scene) => scene.id !== saved.id),
        saved,
      ].sort((left, right) => left.sequence - right.sequence)
      activeSceneId.value = saved.id
      sceneStatus.value = 'Scene contract saved.'
      await loadGraphAnalysis(projectId)
    } catch {
      sceneError.value = 'Scene save failed. Check for duplicate sequence numbers.'
    } finally {
      isSavingScene.value = false
    }
  }
  
  async function deleteSceneContract() {
    sceneError.value = ''
    sceneStatus.value = ''
    const projectId = activeProject.value?.id
    const sceneId = activeSceneId.value
  
    if (!projectId || !sceneId) {
      sceneError.value = 'Select a Scene contract first.'
      return
    }
  
    isDeletingScene.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/scene-contracts/${sceneId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Scene contract')
      }
      sceneContracts.value = sceneContracts.value.filter((scene) => scene.id !== sceneId)
      startNewSceneContract()
      sceneStatus.value = 'Scene contract deleted.'
      await loadGraphAnalysis(projectId)
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
    const projectId = activeProject.value?.id
    const sceneId = activeSceneId.value
  
    if (!projectId || !sceneId) {
      sceneError.value = 'Select a Scene contract first.'
      return
    }
  
    isCompilingScene.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/scene-contracts/${sceneId}/compile`, {
        method: 'POST',
      })
      if (!response.ok) {
        throw new Error('Could not compile Scene contract')
      }
      compileResult.value = await response.json()
      sceneStatus.value = 'Scene compiled.'
    } catch {
      sceneError.value = 'Scene compile failed. Check that the API is running.'
    } finally {
      isCompilingScene.value = false
    }
  }
  
  async function createProposalFromScene(provider = false) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = activeProject.value?.id
    const sceneId = activeSceneId.value
  
    if (!projectId || !sceneId) {
      manuscriptError.value = 'Select a Scene contract first.'
      return
    }
  
    const loadingFlag = provider ? isCreatingProviderProposal : isCreatingProposal
    loadingFlag.value = true
    try {
      const providerPath = provider ? '/provider' : ''
      const response = await fetch(
        `/api/projects/${projectId}/manuscript/proposals/from-scene/${sceneId}${providerPath}`,
        { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not create manuscript proposal')
      }
      const created: ManuscriptProposal = await response.json()
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
  
  async function updateProposalStatus(proposalId: string, status: ManuscriptProposalStatus) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = activeProject.value?.id
  
    if (!projectId) {
      manuscriptError.value = 'Create or select a project first.'
      return
    }
  
    isUpdatingProposal.value = true
    try {
      const response = await fetch(
        `/api/projects/${projectId}/manuscript/proposals/${proposalId}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        }
      )
      if (!response.ok) {
        throw new Error('Could not update manuscript proposal')
      }
      const updated: ManuscriptProposal = await response.json()
      manuscriptProposals.value = manuscriptProposals.value.map((proposal) =>
        proposal.id === updated.id ? updated : proposal
      )
      if (status === 'accepted') {
        await Promise.all([
          loadManuscriptScenes(projectId),
          loadManuscriptRevisions(projectId),
          loadWritebackProposals(projectId),
        ])
      }
      activeProposalId.value = updated.id
      manuscriptStatus.value =
        status === 'accepted' ? 'Proposal accepted.' : 'Proposal rejected.'
    } catch {
      manuscriptError.value = 'Proposal update failed. Check that the API is running.'
    } finally {
      isUpdatingProposal.value = false
    }
  }
  
  async function generateReferenceSuggestion(provider = false) {
    referenceError.value = ''
    referenceStatus.value = ''
    const projectId = activeProject.value?.id
    const authorProblem = referenceDraft.value.author_problem.trim()
  
    if (!projectId) {
      referenceError.value = 'Create or select a project first.'
      return
    }
  
    if (!authorProblem) {
      referenceError.value = 'Describe the writing problem before generating a reference.'
      return
    }
  
    const loadingFlag = provider ? isGeneratingProviderReference : isGeneratingReference
    loadingFlag.value = true
    try {
      const providerPath = provider ? '/provider' : ''
      const response = await fetch(
        `/api/projects/${projectId}/references/suggestions/generate${providerPath}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            suggestion_type: referenceDraft.value.suggestion_type,
            scope_type: referenceDraft.value.scope_type,
            scope_ref: referenceDraft.value.scope_ref.trim(),
            author_problem: authorProblem,
            desired_output: referenceDraft.value.desired_output.trim(),
          }),
        }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not generate reference suggestion')
      }
      const created: ReferenceSuggestion = await response.json()
      referenceSuggestions.value = [
        created,
        ...referenceSuggestions.value.filter((suggestion) => suggestion.id !== created.id),
      ]
      activeReferenceId.value = created.id
      referenceStatus.value = provider
        ? 'Provider reference created for review.'
        : 'Reference created for review.'
    } catch (error) {
      referenceError.value =
        error instanceof Error
          ? `Reference generation failed. ${error.message}`
          : 'Reference generation failed. Check that the API is running.'
    } finally {
      loadingFlag.value = false
    }
  }
  
  async function updateReferenceStatus(
    suggestionId: string,
    status: ReferenceSuggestionStatus,
  ) {
    referenceError.value = ''
    referenceStatus.value = ''
    const projectId = activeProject.value?.id
  
    if (!projectId) {
      referenceError.value = 'Create or select a project first.'
      return
    }
  
    isUpdatingReference.value = true
    try {
      const response = await fetch(
        `/api/projects/${projectId}/references/suggestions/${suggestionId}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        }
      )
      if (!response.ok) {
        throw new Error('Could not update reference suggestion')
      }
      const updated: ReferenceSuggestion = await response.json()
      referenceSuggestions.value = referenceSuggestions.value.map((suggestion) =>
        suggestion.id === updated.id ? updated : suggestion
      )
      activeReferenceId.value = updated.id
      referenceStatus.value =
        status === 'accepted' ? 'Reference accepted.' : 'Reference rejected.'
    } catch {
      referenceError.value = 'Reference update failed. Check that the API is running.'
    } finally {
      isUpdatingReference.value = false
    }
  }
  
  async function loadRevisionDiff() {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    revisionDiff.value = null
    const projectId = activeProject.value?.id
  
    if (!projectId || !diffLeftRevisionId.value || !diffRightRevisionId.value) {
      manuscriptError.value = 'Select two revisions to compare.'
      return
    }
  
    isLoadingDiff.value = true
    try {
      const response = await fetch(
        `/api/projects/${projectId}/manuscript/revisions/${diffLeftRevisionId.value}/diff/${diffRightRevisionId.value}`
      )
      if (!response.ok) {
        throw new Error('Could not load revision diff')
      }
      revisionDiff.value = await response.json()
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
    const projectId = activeProject.value?.id
  
    if (!projectId) {
      manuscriptError.value = 'Create or select a project first.'
      return
    }
  
    isRestoringRevision.value = true
    try {
      const response = await fetch(
        `/api/projects/${projectId}/manuscript/revisions/${revisionId}/restore`,
        { method: 'POST' }
      )
      if (!response.ok) {
        throw new Error('Could not restore revision')
      }
      await loadManuscriptScenes(projectId)
      await loadManuscriptRevisions(projectId)
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
    const projectId = activeProject.value?.id
  
    if (!projectId) {
      manuscriptError.value = 'Create or select a project first.'
      return
    }
  
    isExportingManuscript.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/manuscript/export`)
      if (!response.ok) {
        throw new Error('Could not export manuscript')
      }
      manuscriptExport.value = await response.json()
      manuscriptStatus.value = 'Manuscript export generated.'
    } catch {
      manuscriptError.value = 'Manuscript export failed. Check that the API is running.'
    } finally {
      isExportingManuscript.value = false
    }
  }
  
  function startEditingManuscriptScene(scene: ManuscriptScene) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    editingManuscriptSceneId.value = scene.scene_id
    manuscriptEditTitle.value = scene.title
    manuscriptEditContent.value = scene.content
  }
  
  function cancelEditingManuscriptScene() {
    editingManuscriptSceneId.value = ''
    manuscriptEditTitle.value = ''
    manuscriptEditContent.value = ''
  }
  
  async function saveManuscriptSceneEdit(sceneId: string) {
    manuscriptError.value = ''
    manuscriptStatus.value = ''
    const projectId = activeProject.value?.id
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
  
    isSavingManuscriptScene.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/manuscript/scenes/${sceneId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content }),
      })
      if (!response.ok) {
        throw new Error('Could not save manuscript scene')
      }
      const updated: ManuscriptScene = await response.json()
      manuscriptScenes.value = manuscriptScenes.value.map((scene) =>
        scene.scene_id === updated.scene_id ? updated : scene
      )
      cancelEditingManuscriptScene()
      manuscriptExport.value = null
      revisionDiff.value = null
      await loadManuscriptRevisions(projectId)
      manuscriptStatus.value = `Scene saved as version ${updated.version}.`
    } catch {
      manuscriptError.value = 'Manuscript scene save failed. Check that the API is running.'
    } finally {
      isSavingManuscriptScene.value = false
    }
  }
  
  async function createWritebackFromRevision(revisionId: string, provider = false) {
    writebackError.value = ''
    writebackStatus.value = ''
    const projectId = activeProject.value?.id
  
    if (!projectId) {
      writebackError.value = 'Create or select a project first.'
      return
    }
  
    const loadingFlag = provider ? isCreatingProviderWriteback : isCreatingWriteback
    loadingFlag.value = true
    try {
      const providerPath = provider ? '/provider' : ''
      const response = await fetch(
        `/api/projects/${projectId}/writeback/proposals/from-revision/${revisionId}${providerPath}`,
        { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not create write-back proposals')
      }
      const created: WritebackProposal[] = await response.json()
      writebackProposals.value = [
        ...created,
        ...writebackProposals.value.filter(
          (proposal) => !created.some((item) => item.id === proposal.id)
        ),
      ]
      activeWritebackId.value = created[0]?.id ?? activeWritebackId.value
      writebackStatus.value = created.length
        ? `${created.length} write-back proposal${created.length === 1 ? '' : 's'} created.`
        : 'No write-back proposals were created.'
    } catch (error) {
      writebackError.value =
        error instanceof Error
          ? `Write-back generation failed. ${error.message}`
          : 'Write-back generation failed. Check that the API is running.'
    } finally {
      loadingFlag.value = false
    }
  }
  
  async function processRevisionWithHermes(revisionId: string) {
    writebackError.value = ''
    writebackStatus.value = ''
    hermesProcessReport.value = null
    const projectId = activeProject.value?.id
  
    if (!projectId) {
      writebackError.value = 'Create or select a project first.'
      return
    }
  
    isProcessingHermesRevision.value = true
    try {
      const response = await fetch(
        `/api/projects/${projectId}/writeback/proposals/from-revision/${revisionId}/hermes`,
        { method: 'POST' }
      )
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Could not process revision with Hermes')
      }
      const result: HermesRevisionProcessResponse = await response.json()
      const created = result.writeback_proposals
      writebackProposals.value = [
        ...created,
        ...writebackProposals.value.filter(
          (proposal) => !created.some((item) => item.id === proposal.id)
        ),
      ]
      activeWritebackId.value = created[0]?.id ?? activeWritebackId.value
      hermesProcessReport.value = result
      writebackStatus.value = created.length
        ? `Hermes processed the revision and returned ${created.length} proposal${created.length === 1 ? '' : 's'}.`
        : 'Hermes processed the revision without write-back proposals.'
    } catch (error) {
      writebackError.value =
        error instanceof Error
          ? `Hermes processing failed. ${error.message}`
          : 'Hermes processing failed. Check that the API is running.'
    } finally {
      isProcessingHermesRevision.value = false
    }
  }
  
  async function updateWritebackStatus(proposalId: string, status: WritebackProposalStatus) {
    writebackError.value = ''
    writebackStatus.value = ''
    const projectId = activeProject.value?.id
  
    if (!projectId) {
      writebackError.value = 'Create or select a project first.'
      return
    }
  
    isUpdatingWriteback.value = true
    try {
      const response = await fetch(
        `/api/projects/${projectId}/writeback/proposals/${proposalId}/status`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        }
      )
      if (!response.ok) {
        throw new Error('Could not update write-back proposal')
      }
      const updated: WritebackProposal = await response.json()
      writebackProposals.value = writebackProposals.value.map((proposal) =>
        proposal.id === updated.id ? updated : proposal
      )
      activeWritebackId.value = updated.id
      if (status === 'accepted') {
        await Promise.all([
          loadWritebackProposals(projectId),
          loadGraphAnalysis(projectId),
          refreshCanonAndMemory(projectId),
        ])
      }
      writebackStatus.value =
        status === 'accepted' ? 'Write-back accepted and applied.' : 'Write-back rejected.'
    } catch {
      writebackError.value =
        'Write-back update failed. Check for duplicate Canon names or invalid payloads.'
    } finally {
      isUpdatingWriteback.value = false
    }
  }
  
  async function refreshCanonAndMemory(projectId = activeProject.value?.id) {
    if (!projectId) {
      return
    }
    const [canonResponse, memoryResponse] = await Promise.all([
      fetch(`/api/projects/${projectId}/canon/entities`),
      fetch(`/api/projects/${projectId}/memory/records`),
    ])
    if (!canonResponse.ok || !memoryResponse.ok) {
      throw new Error('Could not refresh Canon and Memory')
    }
    canonEntities.value = await canonResponse.json()
    memoryRecords.value = await memoryResponse.json()
  }
  
  function scenesForChapter(chapterId: string) {
    return sceneContracts.value.filter((scene) => scene.chapter_id === chapterId)
  }
  
  function chapterTitleForScene(sceneId: string) {
    const scene = sceneContracts.value.find((item) => item.id === sceneId)
    const chapter = manuscriptChapters.value.find((item) => item.id === scene?.chapter_id)
    return chapter ? `Chapter ${chapter.sequence}: ${chapter.title}` : 'Unassigned'
  }
  
  function referenceWarnings(suggestion: ReferenceSuggestion) {
    return [
      ...suggestion.canon_warnings,
      ...suggestion.style_notes,
      ...suggestion.graph_warnings,
    ]
  }
  
  function revisionLabel(revision: ManuscriptRevision) {
    return `${revision.title} v${revision.version}`
  }
  
  function statusText(value: string) {
    return value.split('_').join(' ')
  }
  
  function formatJson(value: Record<string, unknown>) {
    return JSON.stringify(value, null, 2)
  }
  
  async function saveMemoryRecord() {
    memoryError.value = ''
    memoryStatus.value = ''
    const projectId = activeProject.value?.id
    const title = memoryDraft.value.title.trim()
    const content = memoryDraft.value.content.trim()
  
    if (!projectId) {
      memoryError.value = 'Create or select a project first.'
      return
    }
  
    if (!title || !content) {
      memoryError.value = 'Title and content are required.'
      return
    }
  
    isSavingMemory.value = true
    try {
      const body = JSON.stringify({
        ...memoryDraft.value,
        title,
        content,
        scope: memoryDraft.value.scope.trim(),
        tags: memoryDraft.value.tags.trim(),
        source_ref: memoryDraft.value.source_ref.trim(),
      })
      const url = activeMemoryId.value
        ? `/api/projects/${projectId}/memory/records/${activeMemoryId.value}`
        : `/api/projects/${projectId}/memory/records`
      const response = await fetch(url, {
        method: activeMemoryId.value ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!response.ok) {
        throw new Error('Could not save Memory record')
      }
      const saved = await response.json()
      memoryRecords.value = [
        ...memoryRecords.value.filter((record) => record.id !== saved.id),
        saved,
      ].sort((left, right) =>
        `${left.record_type}:${left.title}`.localeCompare(`${right.record_type}:${right.title}`)
      )
      activeMemoryId.value = saved.id
      memoryStatus.value = 'Memory / Style record saved.'
      await loadGraphAnalysis(projectId)
    } catch {
      memoryError.value = 'Memory save failed. Check that the API is running.'
    } finally {
      isSavingMemory.value = false
    }
  }
  
  async function deleteMemoryRecord() {
    memoryError.value = ''
    memoryStatus.value = ''
    const projectId = activeProject.value?.id
    const recordId = activeMemoryId.value
  
    if (!projectId || !recordId) {
      memoryError.value = 'Select a Memory / Style record first.'
      return
    }
  
    isDeletingMemory.value = true
    try {
      const response = await fetch(`/api/projects/${projectId}/memory/records/${recordId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error('Could not delete Memory record')
      }
      memoryRecords.value = memoryRecords.value.filter((record) => record.id !== recordId)
      startNewMemoryRecord()
      memoryStatus.value = 'Memory / Style record deleted.'
      await loadGraphAnalysis(projectId)
    } catch {
      memoryError.value = 'Memory delete failed. Check that the API is running.'
    } finally {
      isDeletingMemory.value = false
    }
  }

  return {
    projects,
    steps,
    artifacts,
    canonEntities,
    sceneContracts,
    manuscriptChapters,
    memoryRecords,
    manuscriptProposals,
    manuscriptScenes,
    manuscriptRevisions,
    writebackProposals,
    referenceSuggestions,
    hermesProcessReport,
    activeProjectId,
    activeStepNumber,
    activeSection,
    activeCanonId,
    activeChapterId,
    activeSceneId,
    activeMemoryId,
    activeProposalId,
    activeWritebackId,
    activeReferenceId,
    diffLeftRevisionId,
    diffRightRevisionId,
    editingManuscriptSceneId,
    apiStatus,
    workflowRuntime,
    isCreating,
    isSavingArtifact,
    isGeneratingArtifact,
    isSavingCanon,
    isDeletingCanon,
    isSavingScene,
    isDeletingScene,
    isSavingChapter,
    isDeletingChapter,
    isCompilingScene,
    isSavingMemory,
    isDeletingMemory,
    isLoadingGraph,
    isCreatingProposal,
    isCreatingProviderProposal,
    isUpdatingProposal,
    isSavingManuscriptScene,
    isExportingManuscript,
    isLoadingDiff,
    isRestoringRevision,
    isCreatingWriteback,
    isCreatingProviderWriteback,
    isProcessingHermesRevision,
    isUpdatingWriteback,
    isGeneratingReference,
    isGeneratingProviderReference,
    isUpdatingReference,
    createError,
    artifactError,
    artifactStatus,
    canonError,
    canonStatus,
    chapterError,
    chapterStatus,
    sceneError,
    sceneStatus,
    memoryError,
    memoryStatus,
    graphError,
    manuscriptError,
    manuscriptStatus,
    writebackError,
    writebackStatus,
    referenceError,
    referenceStatus,
    artifactDraft,
    workflowTrace,
    manuscriptEditTitle,
    manuscriptEditContent,
    canonDraft,
    sceneDraft,
    chapterDraft,
    memoryDraft,
    referenceDraft,
    compileResult,
    graphAnalysis,
    revisionDiff,
    manuscriptExport,
    newProject,
    runtimeLabel,
    runtimeTitle,
    activeProject,
    activeStep,
    savedActiveArtifact,
    activeCanonEntity,
    activeChapter,
    activeSceneContract,
    activeMemoryRecord,
    activeProposal,
    activeWritebackProposal,
    activeReferenceSuggestion,
    pendingProposalCount,
    pendingWritebackCount,
    pendingReferenceCount,
    acceptedSceneCount,
    revisionCount,
    unassignedSceneContracts,
    hasUnsavedArtifactChanges,
    artifactStateLabel,
    canonStateLabel,
    sceneStateLabel,
    chapterStateLabel,
    memoryStateLabel,
    createEmptyCanonDraft,
    createEmptySceneDraft,
    createEmptyChapterDraft,
    createEmptyMemoryDraft,
    createEmptyReferenceDraft,
    createProject,
    selectStep,
    upsertArtifact,
    advanceActiveProject,
    loadGraphAnalysis,
    loadManuscriptProposals,
    loadManuscriptChapters,
    loadManuscriptScenes,
    loadManuscriptRevisions,
    loadWritebackProposals,
    loadReferenceSuggestions,
    syncRevisionCompareSelection,
    startNewCanonEntity,
    startNewChapter,
    startNewSceneContract,
    startNewMemoryRecord,
    saveArtifact,
    generateArtifact,
    readErrorDetail,
    saveCanonEntity,
    deleteCanonEntity,
    saveChapter,
    deleteChapter,
    saveSceneContract,
    deleteSceneContract,
    compileSceneContract,
    createProposalFromScene,
    updateProposalStatus,
    generateReferenceSuggestion,
    updateReferenceStatus,
    loadRevisionDiff,
    restoreRevision,
    exportManuscript,
    startEditingManuscriptScene,
    cancelEditingManuscriptScene,
    saveManuscriptSceneEdit,
    createWritebackFromRevision,
    processRevisionWithHermes,
    updateWritebackStatus,
    refreshCanonAndMemory,
    scenesForChapter,
    chapterTitleForScene,
    referenceWarnings,
    revisionLabel,
    statusText,
    formatJson,
    saveMemoryRecord,
    deleteMemoryRecord,
    loadInitialData
  }
})
