<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

type ProjectSummary = {
  id: string
  title: string
  premise: string
  current_step: number
}

type SnowflakeStep = {
  number: number
  title: string
  artifact: string
  description: string
}

type SnowflakeArtifact = {
  project_id: string
  step_number: number
  artifact: string
  content: string
}

type WorkflowAgentTrace = {
  stage: string
  agent_name: string
  status: string
}

type SnowflakeGenerationResponse = SnowflakeArtifact & {
  workflow_trace: WorkflowAgentTrace[]
}

type CanonEntityType = 'character' | 'location' | 'item' | 'faction' | 'rule'

type CanonEntity = {
  id: string
  project_id: string
  entity_type: CanonEntityType
  name: string
  summary: string
  current_state: string
  constraints: string
  last_seen: string
  timeline_notes: string
}

type CanonDraft = Omit<CanonEntity, 'id' | 'project_id'>

type SceneContract = {
  id: string
  project_id: string
  sequence: number
  title: string
  pov: string
  goal: string
  conflict: string
  turning_point: string
  required_canon: string
  forbidden_facts: string
  open_threads: string
  source_artifact_step: number
}

type SceneDraft = Omit<SceneContract, 'id' | 'project_id'>

type MemoryRecordType = 'chapter_summary' | 'prose_sample' | 'voice_sample' | 'style_rule'

type MemoryRecord = {
  id: string
  project_id: string
  record_type: MemoryRecordType
  title: string
  scope: string
  content: string
  tags: string
  source_ref: string
}

type MemoryDraft = Omit<MemoryRecord, 'id' | 'project_id'>

type ChapterCompileResponse = {
  project_id: string
  scene_id: string
  context: string
  draft: string
  checklist: string[]
}

type ManuscriptProposalStatus = 'pending_review' | 'accepted' | 'rejected'

type ManuscriptProposal = {
  id: string
  project_id: string
  scene_id: string
  source: 'scene_contract'
  title: string
  content: string
  context: string
  checklist: string[]
  status: ManuscriptProposalStatus
  created_at: string
  reviewed_at: string
}

type ManuscriptScene = {
  id: string
  project_id: string
  scene_id: string
  proposal_id: string
  title: string
  content: string
  version: number
  accepted_at: string
}

type ManuscriptRevision = {
  id: string
  project_id: string
  scene_id: string
  proposal_id: string
  title: string
  content: string
  version: number
  created_at: string
}

type ManuscriptRevisionDiff = {
  project_id: string
  left_revision_id: string
  right_revision_id: string
  left_title: string
  right_title: string
  diff_lines: string[]
}

type ManuscriptExport = {
  project_id: string
  title: string
  scene_count: number
  content: string
  generated_at: string
}

type WritebackProposalStatus = 'pending_review' | 'accepted' | 'rejected'
type WritebackTarget = 'canon_entity' | 'memory_record'

type WritebackProposal = {
  id: string
  project_id: string
  target: WritebackTarget
  action: 'create'
  title: string
  rationale: string
  payload: Record<string, unknown>
  source_ref: string
  status: WritebackProposalStatus
  created_at: string
  reviewed_at: string
  applied_record_id: string
}

type HermesWikiChange = {
  path: string
  action: 'created' | 'updated' | 'skipped'
  reason: string
}

type HermesProcessingIssue = {
  severity: 'info' | 'warning' | 'error'
  code: string
  message: string
  source_ref: string
}

type HermesRevisionProcessResponse = {
  status: 'completed' | 'partial' | 'failed'
  summary: string
  wiki_changes: HermesWikiChange[]
  issues: HermesProcessingIssue[]
  writeback_proposals: WritebackProposal[]
  processed_source_ref: string
}

type GraphNode = {
  id: string
  label: string
  node_type: string
  status: string
}

type GraphEdge = {
  source: string
  target: string
  edge_type: string
  label: string
}

type GraphRisk = {
  id: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  detail: string
  source_id: string
}

type GraphAnalysisSummary = {
  node_count: number
  edge_count: number
  risk_count: number
  critical_count: number
  warning_count: number
  unresolved_thread_count: number
  canon_reference_count: number
}

type GraphAnalysisResponse = {
  project_id: string
  summary: GraphAnalysisSummary
  nodes: GraphNode[]
  edges: GraphEdge[]
  risks: GraphRisk[]
}

type WorkflowRuntimeStatus = {
  runtime: 'local_deterministic' | 'provider_deepseek'
  provider: string
  provider_configured: boolean
  model: string
  base_url: string
  details: string
}

type ActiveSection = 'snowflake' | 'canon' | 'memory' | 'graph' | 'manuscript'

const projects = ref<ProjectSummary[]>([])
const steps = ref<SnowflakeStep[]>([])
const artifacts = ref<SnowflakeArtifact[]>([])
const canonEntities = ref<CanonEntity[]>([])
const sceneContracts = ref<SceneContract[]>([])
const memoryRecords = ref<MemoryRecord[]>([])
const manuscriptProposals = ref<ManuscriptProposal[]>([])
const manuscriptScenes = ref<ManuscriptScene[]>([])
const manuscriptRevisions = ref<ManuscriptRevision[]>([])
const writebackProposals = ref<WritebackProposal[]>([])
const hermesProcessReport = ref<HermesRevisionProcessResponse | null>(null)
const activeProjectId = ref('')
const activeStepNumber = ref(1)
const activeSection = ref<ActiveSection>('snowflake')
const activeCanonId = ref('')
const activeSceneId = ref('')
const activeMemoryId = ref('')
const activeProposalId = ref('')
const activeWritebackId = ref('')
const diffLeftRevisionId = ref('')
const diffRightRevisionId = ref('')
const editingManuscriptSceneId = ref('')
const apiStatus = ref('checking')
const workflowRuntime = ref<WorkflowRuntimeStatus | null>(null)
const isCreating = ref(false)
const isSavingArtifact = ref(false)
const isGeneratingArtifact = ref(false)
const isSavingCanon = ref(false)
const isDeletingCanon = ref(false)
const isSavingScene = ref(false)
const isDeletingScene = ref(false)
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
const createError = ref('')
const artifactError = ref('')
const artifactStatus = ref('')
const canonError = ref('')
const canonStatus = ref('')
const sceneError = ref('')
const sceneStatus = ref('')
const memoryError = ref('')
const memoryStatus = ref('')
const graphError = ref('')
const manuscriptError = ref('')
const manuscriptStatus = ref('')
const writebackError = ref('')
const writebackStatus = ref('')
const artifactDraft = ref('')
const workflowTrace = ref<WorkflowAgentTrace[]>([])
const manuscriptEditTitle = ref('')
const manuscriptEditContent = ref('')
const canonDraft = ref<CanonDraft>(createEmptyCanonDraft())
const sceneDraft = ref<SceneDraft>(createEmptySceneDraft())
const memoryDraft = ref<MemoryDraft>(createEmptyMemoryDraft())
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

const pendingProposalCount = computed(
  () => manuscriptProposals.value.filter((proposal) => proposal.status === 'pending_review').length
)

const pendingWritebackCount = computed(
  () => writebackProposals.value.filter((proposal) => proposal.status === 'pending_review').length
)

const acceptedSceneCount = computed(() => manuscriptScenes.value.length)

const revisionCount = computed(() => manuscriptRevisions.value.length)

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

onMounted(async () => {
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
})

watch(activeProjectId, async (projectId) => {
  artifactError.value = ''
  artifactStatus.value = ''
  workflowTrace.value = []
  canonError.value = ''
  canonStatus.value = ''
  sceneError.value = ''
  sceneStatus.value = ''
  memoryError.value = ''
  memoryStatus.value = ''
  graphError.value = ''
  manuscriptError.value = ''
  manuscriptStatus.value = ''
  writebackError.value = ''
  writebackStatus.value = ''
  artifacts.value = []
  canonEntities.value = []
  sceneContracts.value = []
  memoryRecords.value = []
  manuscriptProposals.value = []
  manuscriptScenes.value = []
  manuscriptRevisions.value = []
  writebackProposals.value = []
  hermesProcessReport.value = null
  graphAnalysis.value = null
  revisionDiff.value = null
  manuscriptExport.value = null
  compileResult.value = null
  artifactDraft.value = ''
  activeCanonId.value = ''
  activeSceneId.value = ''
  activeMemoryId.value = ''
  activeProposalId.value = ''
  activeWritebackId.value = ''
  diffLeftRevisionId.value = ''
  diffRightRevisionId.value = ''
  editingManuscriptSceneId.value = ''
  manuscriptEditTitle.value = ''
  manuscriptEditContent.value = ''
  canonDraft.value = createEmptyCanonDraft()
  sceneDraft.value = createEmptySceneDraft()
  memoryDraft.value = createEmptyMemoryDraft()

  const project = projects.value.find((item) => item.id === projectId)
  activeStepNumber.value = project?.current_step ?? 1

  if (!projectId) {
    return
  }

  try {
    const [
      artifactResponse,
      canonResponse,
      sceneResponse,
      memoryResponse,
      proposalResponse,
      manuscriptSceneResponse,
      manuscriptRevisionResponse,
      writebackResponse,
    ] =
      await Promise.all([
        fetch(`/api/projects/${projectId}/snowflake/artifacts`),
        fetch(`/api/projects/${projectId}/canon/entities`),
        fetch(`/api/projects/${projectId}/scene-contracts`),
        fetch(`/api/projects/${projectId}/memory/records`),
        fetch(`/api/projects/${projectId}/manuscript/proposals`),
        fetch(`/api/projects/${projectId}/manuscript/scenes`),
        fetch(`/api/projects/${projectId}/manuscript/revisions`),
        fetch(`/api/projects/${projectId}/writeback/proposals`),
      ])
    if (
      !artifactResponse.ok ||
      !canonResponse.ok ||
      !sceneResponse.ok ||
      !memoryResponse.ok ||
      !proposalResponse.ok ||
      !manuscriptSceneResponse.ok ||
      !manuscriptRevisionResponse.ok ||
      !writebackResponse.ok
    ) {
      throw new Error('Could not load artifacts')
    }
    artifacts.value = await artifactResponse.json()
    canonEntities.value = await canonResponse.json()
    sceneContracts.value = await sceneResponse.json()
    memoryRecords.value = await memoryResponse.json()
    manuscriptProposals.value = await proposalResponse.json()
    manuscriptScenes.value = await manuscriptSceneResponse.json()
    manuscriptRevisions.value = await manuscriptRevisionResponse.json()
    writebackProposals.value = await writebackResponse.json()
    activeProposalId.value = manuscriptProposals.value[0]?.id ?? ''
    activeWritebackId.value = writebackProposals.value[0]?.id ?? ''
    syncRevisionCompareSelection()
    artifactDraft.value = savedActiveArtifact.value?.content ?? ''
    await loadGraphAnalysis(projectId)
  } catch {
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

watch(activeSceneId, () => {
  sceneError.value = ''
  sceneStatus.value = ''
  compileResult.value = null
  const selected = activeSceneContract.value
  sceneDraft.value = selected
    ? {
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

async function loadGraphAnalysis(projectId = activeProject.value?.id) {
  graphError.value = ''
  if (!projectId) {
    graphAnalysis.value = null
    return
  }

  isLoadingGraph.value = true
  try {
    const response = await fetch(`/api/projects/${projectId}/graph/analysis`)
    if (!response.ok) {
      throw new Error('Could not load graph analysis')
    }
    graphAnalysis.value = await response.json()
  } catch {
    graphError.value = 'Graph analysis could not be loaded.'
  } finally {
    isLoadingGraph.value = false
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

function startNewSceneContract() {
  activeSceneId.value = ''
  sceneDraft.value = {
    ...createEmptySceneDraft(),
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
      await loadManuscriptScenes(projectId)
      await loadManuscriptRevisions(projectId)
      await loadWritebackProposals(projectId)
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

function revisionLabel(revision: ManuscriptRevision) {
  return `${revision.title} v${revision.version}`
}

function statusText(value: string) {
  return value.replace('_', ' ')
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
</script>

<template>
  <main class="shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="mark">AW</span>
        <div>
          <h1>AI Writing Studio</h1>
          <p>Snowflake compiler for long-form fiction</p>
        </div>
      </div>

      <nav class="nav">
        <button :class="{ active: activeSection === 'snowflake' }" @click="activeSection = 'snowflake'">
          Snowflake
        </button>
        <button :class="{ active: activeSection === 'canon' }" @click="activeSection = 'canon'">
          Canon
        </button>
        <button :class="{ active: activeSection === 'memory' }" @click="activeSection = 'memory'">
          Memory
        </button>
        <button :class="{ active: activeSection === 'graph' }" @click="activeSection = 'graph'">
          Graph
        </button>
        <button
          :class="{ active: activeSection === 'manuscript' }"
          @click="activeSection = 'manuscript'"
        >
          Manuscript
        </button>
      </nav>

      <section class="project-list" aria-label="Projects">
        <p class="section-label">Projects</p>
        <button
          v-for="project in projects"
          :key="project.id"
          :class="{ active: project.id === activeProjectId }"
          @click="activeProjectId = project.id"
        >
          <span>{{ project.title }}</span>
          <small>Step {{ project.current_step }}</small>
        </button>
      </section>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Project</p>
          <h2>{{ activeProject?.title ?? 'No Project' }}</h2>
          <p class="premise">{{ activeProject?.premise ?? 'Create a project to begin.' }}</p>
        </div>
        <div class="status-stack">
          <span class="status" :class="{ offline: apiStatus !== 'ok' }">
            API {{ apiStatus }}
          </span>
          <span
            class="status runtime"
            :class="{ local: workflowRuntime?.runtime !== 'provider_deepseek' }"
            :title="runtimeTitle"
          >
            {{ runtimeLabel }}
          </span>
        </div>
      </header>

      <section
        v-if="activeSection === 'snowflake'"
        class="create-project"
        aria-labelledby="create-project-title"
      >
        <div>
          <p class="eyebrow">New Project</p>
          <h3 id="create-project-title">Start a Snowflake draft</h3>
        </div>

        <form @submit.prevent="createProject">
          <label>
            <span>Title</span>
            <input v-model="newProject.title" autocomplete="off" placeholder="The Glass City" />
          </label>
          <label>
            <span>Premise</span>
            <textarea
              v-model="newProject.premise"
              rows="3"
              placeholder="A disgraced cartographer discovers the city map is rewriting its people."
            />
          </label>
          <div class="form-actions">
            <p v-if="createError" class="error">{{ createError }}</p>
            <button class="primary" type="submit" :disabled="isCreating">
              {{ isCreating ? 'Creating...' : 'Create Project' }}
            </button>
          </div>
        </form>
      </section>

      <section v-if="activeSection === 'snowflake'" class="pipeline">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Compiler Pipeline</p>
            <h3>Snowflake Method</h3>
          </div>
          <span class="step-chip">Current step {{ activeProject?.current_step ?? 1 }}</span>
        </div>

        <ol class="steps">
          <li
            v-for="step in steps"
            :key="step.number"
            :class="{
              current: step.number === activeStepNumber,
              saved: artifacts.some((artifact) => artifact.step_number === step.number),
            }"
          >
            <button
              class="step-selector"
              type="button"
              :aria-label="`Open step ${step.number}: ${step.title}`"
              @click="selectStep(step.number)"
            >
              <span class="step-number">{{ step.number }}</span>
            </button>
            <div>
              <h4>{{ step.title }}</h4>
              <p>{{ step.description }}</p>
              <code>{{ step.artifact }}</code>
            </div>
          </li>
        </ol>
      </section>

      <section
        v-if="activeSection === 'snowflake'"
        class="artifact-editor"
        aria-labelledby="artifact-editor-title"
      >
        <div class="panel-header">
          <div>
            <p class="eyebrow">Active Artifact</p>
            <h3 id="artifact-editor-title">
              Step {{ activeStep?.number ?? 1 }}: {{ activeStep?.title ?? 'Snowflake Step' }}
            </h3>
          </div>
          <span class="step-chip">{{ activeStep?.artifact ?? 'artifact' }}</span>
        </div>

        <textarea
          v-model="artifactDraft"
          rows="12"
          :disabled="!activeProject"
          :placeholder="`Write the ${activeStep?.artifact ?? 'artifact'} for the active project.`"
        />

        <div class="form-actions artifact-actions">
          <p v-if="artifactError" class="error">{{ artifactError }}</p>
          <p v-else class="save-state">{{ artifactStateLabel }}</p>
          <div class="button-row">
            <button
              class="secondary"
              type="button"
              :disabled="isGeneratingArtifact || !activeProject"
              @click="generateArtifact"
            >
              {{ isGeneratingArtifact ? 'Generating...' : 'Generate Draft' }}
            </button>
            <button
              class="primary"
              type="button"
              :disabled="isSavingArtifact || !hasUnsavedArtifactChanges"
              @click="saveArtifact"
            >
              {{ isSavingArtifact ? 'Saving...' : 'Save Artifact' }}
            </button>
          </div>
        </div>

        <ol v-if="workflowTrace.length" class="trace-list" aria-label="Workflow trace">
          <li v-for="trace in workflowTrace" :key="`${trace.stage}-${trace.agent_name}`">
            <span>{{ trace.stage }}</span>
            <strong>{{ trace.agent_name }}</strong>
            <small>{{ trace.status }}</small>
          </li>
        </ol>
      </section>

      <section v-if="activeSection === 'canon'" class="canon-workspace">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Canon DB</p>
            <h3>Confirmed Story Facts</h3>
          </div>
          <button class="primary" type="button" @click="startNewCanonEntity">
            New Canon Entity
          </button>
        </div>

        <div class="canon-grid">
          <aside class="canon-list" aria-label="Canon entities">
            <button
              v-for="entity in canonEntities"
              :key="entity.id"
              :class="{ active: entity.id === activeCanonId }"
              type="button"
              @click="activeCanonId = entity.id"
            >
              <span>{{ entity.name }}</span>
              <small>{{ entity.entity_type }}</small>
            </button>
            <p v-if="canonEntities.length === 0" class="empty-state">
              No Canon entities yet.
            </p>
          </aside>

          <form class="canon-editor" @submit.prevent="saveCanonEntity">
            <div class="canon-fields">
              <label>
                <span>Type</span>
                <select v-model="canonDraft.entity_type">
                  <option value="character">Character</option>
                  <option value="location">Location</option>
                  <option value="item">Item</option>
                  <option value="faction">Faction</option>
                  <option value="rule">Rule</option>
                </select>
              </label>
              <label>
                <span>Name</span>
                <input v-model="canonDraft.name" autocomplete="off" placeholder="Lin Ye" />
              </label>
            </div>

            <label>
              <span>Summary</span>
              <textarea
                v-model="canonDraft.summary"
                rows="3"
                placeholder="What this entity is and why it matters."
              />
            </label>
            <label>
              <span>Current State</span>
              <textarea
                v-model="canonDraft.current_state"
                rows="4"
                placeholder="Confirmed facts at the current point in the story."
              />
            </label>
            <label>
              <span>Constraints</span>
              <textarea
                v-model="canonDraft.constraints"
                rows="4"
                placeholder="Facts future drafts must not violate."
              />
            </label>
            <div class="canon-fields">
              <label>
                <span>Last Seen</span>
                <input v-model="canonDraft.last_seen" placeholder="chapter_12 or scene S032" />
              </label>
            </div>
            <label>
              <span>Timeline Notes</span>
              <textarea
                v-model="canonDraft.timeline_notes"
                rows="5"
                placeholder="Important state changes by chapter or scene."
              />
            </label>

            <div class="form-actions artifact-actions">
              <p v-if="canonError" class="error">{{ canonError }}</p>
              <p v-else class="save-state">{{ canonStateLabel }}</p>
              <div class="button-row">
                <button
                  v-if="activeCanonId"
                  class="secondary danger"
                  type="button"
                  :disabled="isDeletingCanon"
                  @click="deleteCanonEntity"
                >
                  {{ isDeletingCanon ? 'Deleting...' : 'Delete' }}
                </button>
                <button class="primary" type="submit" :disabled="isSavingCanon">
                  {{ isSavingCanon ? 'Saving...' : activeCanonId ? 'Save Entity' : 'Create Entity' }}
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>

      <section v-if="activeSection === 'memory'" class="memory-workspace">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Memory / Style</p>
            <h3>Continuity Records</h3>
          </div>
          <button class="primary" type="button" @click="startNewMemoryRecord">
            New Memory Record
          </button>
        </div>

        <div class="memory-grid">
          <aside class="memory-list" aria-label="Memory and style records">
            <button
              v-for="record in memoryRecords"
              :key="record.id"
              :class="{ active: record.id === activeMemoryId }"
              type="button"
              @click="activeMemoryId = record.id"
            >
              <span>{{ record.title }}</span>
              <small>{{ record.record_type.replace('_', ' ') }}</small>
            </button>
            <p v-if="memoryRecords.length === 0" class="empty-state">
              No Memory / Style records yet.
            </p>
          </aside>

          <form class="memory-editor" @submit.prevent="saveMemoryRecord">
            <div class="memory-fields">
              <label>
                <span>Type</span>
                <select v-model="memoryDraft.record_type">
                  <option value="chapter_summary">Chapter Summary</option>
                  <option value="prose_sample">Prose Sample</option>
                  <option value="voice_sample">Voice Sample</option>
                  <option value="style_rule">Style Rule</option>
                </select>
              </label>
              <label>
                <span>Title</span>
                <input v-model="memoryDraft.title" autocomplete="off" placeholder="Chapter 3 recap" />
              </label>
            </div>

            <div class="memory-fields">
              <label>
                <span>Scope</span>
                <input v-model="memoryDraft.scope" placeholder="chapter_03, Lin voice, city prose" />
              </label>
              <label>
                <span>Source</span>
                <input v-model="memoryDraft.source_ref" placeholder="manuscript/chapter_03" />
              </label>
            </div>

            <label>
              <span>Content</span>
              <textarea
                v-model="memoryDraft.content"
                rows="10"
                placeholder="Summary, sample prose, voice notes, or style rules."
              />
            </label>
            <label>
              <span>Tags</span>
              <input v-model="memoryDraft.tags" placeholder="quiet tension, Lin, archive" />
            </label>

            <div class="form-actions artifact-actions">
              <p v-if="memoryError" class="error">{{ memoryError }}</p>
              <p v-else class="save-state">{{ memoryStateLabel }}</p>
              <div class="button-row">
                <button
                  v-if="activeMemoryId"
                  class="secondary danger"
                  type="button"
                  :disabled="isDeletingMemory"
                  @click="deleteMemoryRecord"
                >
                  {{ isDeletingMemory ? 'Deleting...' : 'Delete' }}
                </button>
                <button class="primary" type="submit" :disabled="isSavingMemory">
                  {{
                    isSavingMemory
                      ? 'Saving...'
                      : activeMemoryId
                        ? 'Save Record'
                        : 'Create Record'
                  }}
                </button>
              </div>
            </div>
          </form>
        </div>
      </section>

      <section v-if="activeSection === 'graph'" class="graph-workspace">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Graph / Structure</p>
            <h3>Narrative Analysis</h3>
          </div>
          <button
            class="secondary"
            type="button"
            :disabled="isLoadingGraph || !activeProject"
            @click="loadGraphAnalysis()"
          >
            {{ isLoadingGraph ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <p v-if="graphError" class="error">{{ graphError }}</p>
        <p v-else-if="!graphAnalysis" class="empty-state">
          No graph analysis loaded.
        </p>

        <template v-if="graphAnalysis">
          <div class="graph-summary" aria-label="Graph summary">
            <div>
              <span>{{ graphAnalysis.summary.node_count }}</span>
              <small>Nodes</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.edge_count }}</span>
              <small>Edges</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.risk_count }}</span>
              <small>Risks</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.unresolved_thread_count }}</span>
              <small>Open Threads</small>
            </div>
            <div>
              <span>{{ graphAnalysis.summary.canon_reference_count }}</span>
              <small>Canon Refs</small>
            </div>
          </div>

          <section class="graph-panel">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">Review Queue</p>
                <h4>Structural Risks</h4>
              </div>
              <span class="step-chip">
                {{ graphAnalysis.summary.critical_count }} critical /
                {{ graphAnalysis.summary.warning_count }} warning
              </span>
            </div>
            <div class="risk-list">
              <article
                v-for="risk in graphAnalysis.risks"
                :key="risk.id"
                class="risk-item"
                :class="risk.severity"
              >
                <strong>{{ risk.title }}</strong>
                <p>{{ risk.detail }}</p>
                <small>{{ risk.severity }} · {{ risk.source_id || 'project' }}</small>
              </article>
              <p v-if="graphAnalysis.risks.length === 0" class="empty-state">
                No structural risks detected.
              </p>
            </div>
          </section>

          <div class="graph-tables">
            <section class="graph-panel">
              <p class="eyebrow">Nodes</p>
              <div class="graph-table">
                <div v-for="node in graphAnalysis.nodes" :key="node.id" class="graph-row">
                  <strong>{{ node.label }}</strong>
                  <span>{{ node.node_type }}</span>
                  <small>{{ node.status || node.id }}</small>
                </div>
              </div>
            </section>
            <section class="graph-panel">
              <p class="eyebrow">Edges</p>
              <div class="graph-table">
                <div
                  v-for="edge in graphAnalysis.edges"
                  :key="`${edge.source}-${edge.edge_type}-${edge.target}-${edge.label}`"
                  class="graph-row"
                >
                  <strong>{{ edge.edge_type }}</strong>
                  <span>{{ edge.source }} -> {{ edge.target }}</span>
                  <small>{{ edge.label || 'link' }}</small>
                </div>
              </div>
            </section>
          </div>
        </template>
      </section>

      <section v-if="activeSection === 'manuscript'" class="manuscript-workspace">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Scene Contracts</p>
            <h3>Manuscript Inputs</h3>
          </div>
          <button class="primary" type="button" @click="startNewSceneContract">
            New Scene
          </button>
        </div>

        <div class="scene-grid">
          <aside class="scene-list" aria-label="Scene contracts">
            <button
              v-for="scene in sceneContracts"
              :key="scene.id"
              :class="{ active: scene.id === activeSceneId }"
              type="button"
              @click="activeSceneId = scene.id"
            >
              <span>{{ scene.sequence }}. {{ scene.title }}</span>
              <small>{{ scene.pov || 'No POV' }}</small>
            </button>
            <p v-if="sceneContracts.length === 0" class="empty-state">
              No Scene contracts yet.
            </p>
          </aside>

          <form class="scene-editor" @submit.prevent="saveSceneContract">
            <div class="scene-fields">
              <label>
                <span>Sequence</span>
                <input v-model.number="sceneDraft.sequence" type="number" min="1" max="999" />
              </label>
              <label>
                <span>Title</span>
                <input v-model="sceneDraft.title" autocomplete="off" placeholder="The map changes" />
              </label>
              <label>
                <span>POV</span>
                <input v-model="sceneDraft.pov" autocomplete="off" placeholder="Lin Ye" />
              </label>
              <label>
                <span>Source Step</span>
                <input
                  v-model.number="sceneDraft.source_artifact_step"
                  type="number"
                  min="1"
                  max="10"
                />
              </label>
            </div>

            <label>
              <span>Goal</span>
              <textarea v-model="sceneDraft.goal" rows="3" placeholder="What the POV wants." />
            </label>
            <label>
              <span>Conflict</span>
              <textarea
                v-model="sceneDraft.conflict"
                rows="3"
                placeholder="What blocks the goal."
              />
            </label>
            <label>
              <span>Turning Point</span>
              <textarea
                v-model="sceneDraft.turning_point"
                rows="3"
                placeholder="What changes by the end."
              />
            </label>
            <label>
              <span>Required Canon</span>
              <textarea
                v-model="sceneDraft.required_canon"
                rows="4"
                placeholder="Facts this scene must respect."
              />
            </label>
            <label>
              <span>Forbidden Facts</span>
              <textarea
                v-model="sceneDraft.forbidden_facts"
                rows="4"
                placeholder="Facts this scene cannot reveal or contradict."
              />
            </label>
            <label>
              <span>Open Threads</span>
              <textarea
                v-model="sceneDraft.open_threads"
                rows="4"
                placeholder="Questions advanced or opened by this scene."
              />
            </label>

            <div class="form-actions artifact-actions">
              <p v-if="sceneError" class="error">{{ sceneError }}</p>
              <p v-else class="save-state">{{ sceneStateLabel }}</p>
              <div class="button-row">
                <button
                  v-if="activeSceneId"
                  class="secondary danger"
                  type="button"
                  :disabled="isDeletingScene"
                  @click="deleteSceneContract"
                >
                  {{ isDeletingScene ? 'Deleting...' : 'Delete' }}
                </button>
                <button
                  v-if="activeSceneId"
                  class="secondary"
                  type="button"
                  :disabled="isCompilingScene"
                  @click="compileSceneContract"
                >
                  {{ isCompilingScene ? 'Compiling...' : 'Compile' }}
                </button>
                <button
                  v-if="activeSceneId"
                  class="secondary"
                  type="button"
                  :disabled="isCreatingProposal"
                  @click="createProposalFromScene()"
                >
                  {{ isCreatingProposal ? 'Creating...' : 'Create Proposal' }}
                </button>
                <button
                  v-if="activeSceneId"
                  class="secondary"
                  type="button"
                  :disabled="isCreatingProviderProposal"
                  @click="createProposalFromScene(true)"
                >
                  {{ isCreatingProviderProposal ? 'Creating...' : 'Provider Proposal' }}
                </button>
                <button class="primary" type="submit" :disabled="isSavingScene">
                  {{ isSavingScene ? 'Saving...' : activeSceneId ? 'Save Scene' : 'Create Scene' }}
                </button>
              </div>
            </div>
          </form>
        </div>

        <div v-if="compileResult" class="compile-output">
          <section>
            <p class="eyebrow">Context Package</p>
            <pre>{{ compileResult.context }}</pre>
          </section>
          <section>
            <p class="eyebrow">Draft Placeholder</p>
            <pre>{{ compileResult.draft }}</pre>
          </section>
          <section>
            <p class="eyebrow">Checklist</p>
            <ul>
              <li v-for="item in compileResult.checklist" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>

        <section class="proposal-workspace">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Review Queue</p>
              <h3>Manuscript Proposals</h3>
            </div>
            <div class="button-row">
              <span class="step-chip">{{ pendingProposalCount }} pending</span>
              <span class="step-chip">{{ acceptedSceneCount }} accepted scenes</span>
              <span class="step-chip">{{ revisionCount }} revisions</span>
              <span class="step-chip">{{ pendingWritebackCount }} write-backs</span>
            </div>
          </div>

          <p v-if="manuscriptError" class="error">{{ manuscriptError }}</p>
          <p v-else-if="manuscriptStatus" class="save-state">{{ manuscriptStatus }}</p>

          <div class="proposal-grid">
            <aside class="proposal-list" aria-label="Manuscript proposals">
              <button
                v-for="proposal in manuscriptProposals"
                :key="proposal.id"
                :class="{ active: proposal.id === activeProposalId }"
                type="button"
                @click="activeProposalId = proposal.id"
              >
                <span>{{ proposal.title }}</span>
                <small>{{ statusText(proposal.status) }}</small>
              </button>
              <p v-if="manuscriptProposals.length === 0" class="empty-state">
                No manuscript proposals yet.
              </p>
            </aside>

            <section v-if="activeProposal" class="proposal-detail">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">{{ statusText(activeProposal.status) }}</p>
                  <h4>{{ activeProposal.title }}</h4>
                </div>
                <div class="button-row">
                  <button
                    v-if="activeProposal.status === 'pending_review'"
                    class="secondary danger"
                    type="button"
                    :disabled="isUpdatingProposal"
                    @click="updateProposalStatus(activeProposal.id, 'rejected')"
                  >
                    Reject
                  </button>
                  <button
                    v-if="activeProposal.status === 'pending_review'"
                    class="primary"
                    type="button"
                    :disabled="isUpdatingProposal"
                    @click="updateProposalStatus(activeProposal.id, 'accepted')"
                  >
                    Accept
                  </button>
                </div>
              </div>

              <section>
                <p class="eyebrow">Proposed Draft</p>
                <pre>{{ activeProposal.content }}</pre>
              </section>
              <section>
                <p class="eyebrow">Review Checklist</p>
                <ul>
                  <li v-for="item in activeProposal.checklist" :key="item">{{ item }}</li>
                </ul>
              </section>
              <section>
                <p class="eyebrow">Source Context</p>
                <pre>{{ activeProposal.context }}</pre>
              </section>
            </section>
          </div>
        </section>

        <section class="accepted-manuscript">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Accepted Manuscript</p>
              <h3>Current Scene Drafts</h3>
            </div>
            <div class="button-row">
              <button
                class="secondary"
                type="button"
                :disabled="isExportingManuscript"
                @click="exportManuscript"
              >
                {{ isExportingManuscript ? 'Exporting...' : 'Export Markdown' }}
              </button>
              <button class="secondary" type="button" @click="loadManuscriptScenes()">
                Refresh
              </button>
            </div>
          </div>

          <section v-if="manuscriptExport" class="export-output">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">{{ manuscriptExport.scene_count }} scenes</p>
                <h4>{{ manuscriptExport.title }}</h4>
              </div>
              <small>{{ manuscriptExport.generated_at }}</small>
            </div>
            <pre>{{ manuscriptExport.content }}</pre>
          </section>

          <div class="accepted-list">
            <article v-for="scene in manuscriptScenes" :key="scene.id" class="accepted-item">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">Version {{ scene.version }}</p>
                  <h4>{{ scene.title }}</h4>
                </div>
                <div class="revision-actions">
                  <small>{{ scene.accepted_at }}</small>
                  <div class="button-row">
                    <button
                      v-if="editingManuscriptSceneId !== scene.scene_id"
                      class="secondary"
                      type="button"
                      @click="startEditingManuscriptScene(scene)"
                    >
                      Edit
                    </button>
                  </div>
                </div>
              </div>
              <form
                v-if="editingManuscriptSceneId === scene.scene_id"
                class="manuscript-edit"
                @submit.prevent="saveManuscriptSceneEdit(scene.scene_id)"
              >
                <label>
                  <span>Title</span>
                  <input v-model="manuscriptEditTitle" autocomplete="off" />
                </label>
                <label>
                  <span>Content</span>
                  <textarea v-model="manuscriptEditContent" rows="14" />
                </label>
                <div class="form-actions artifact-actions">
                  <p class="save-state">Saving creates a new manuscript revision.</p>
                  <div class="button-row">
                    <button class="secondary" type="button" @click="cancelEditingManuscriptScene">
                      Cancel
                    </button>
                    <button class="primary" type="submit" :disabled="isSavingManuscriptScene">
                      {{ isSavingManuscriptScene ? 'Saving...' : 'Save Version' }}
                    </button>
                  </div>
                </div>
              </form>
              <pre v-else>{{ scene.content }}</pre>
            </article>
            <p v-if="manuscriptScenes.length === 0" class="empty-state">
              No accepted manuscript scenes yet.
            </p>
          </div>
        </section>

        <section class="revision-history">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Version History</p>
              <h3>Accepted Revisions</h3>
            </div>
            <button class="secondary" type="button" @click="loadManuscriptRevisions()">
              Refresh
            </button>
          </div>

          <div v-if="manuscriptRevisions.length" class="revision-tools">
            <label>
              <span>Base Revision</span>
              <select v-model="diffLeftRevisionId">
                <option
                  v-for="revision in manuscriptRevisions"
                  :key="`left-${revision.id}`"
                  :value="revision.id"
                >
                  {{ revisionLabel(revision) }}
                </option>
              </select>
            </label>
            <label>
              <span>Compare Revision</span>
              <select v-model="diffRightRevisionId">
                <option
                  v-for="revision in manuscriptRevisions"
                  :key="`right-${revision.id}`"
                  :value="revision.id"
                >
                  {{ revisionLabel(revision) }}
                </option>
              </select>
            </label>
            <button class="secondary" type="button" :disabled="isLoadingDiff" @click="loadRevisionDiff">
              {{ isLoadingDiff ? 'Loading...' : 'Compare' }}
            </button>
          </div>

          <section v-if="revisionDiff" class="diff-output">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">Revision Diff</p>
                <h4>{{ revisionDiff.left_title }} -> {{ revisionDiff.right_title }}</h4>
              </div>
              <span class="step-chip">{{ revisionDiff.diff_lines.length }} lines</span>
            </div>
            <pre>{{ revisionDiff.diff_lines.join('\n') }}</pre>
          </section>

          <div class="revision-list">
            <article v-for="revision in manuscriptRevisions" :key="revision.id" class="revision-item">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">Version {{ revision.version }}</p>
                  <h4>{{ revision.title }}</h4>
                </div>
                <div class="revision-actions">
                  <small>{{ revision.created_at }}</small>
                  <div class="button-row">
                    <button
                      class="secondary"
                      type="button"
                      :disabled="isProcessingHermesRevision"
                      @click="processRevisionWithHermes(revision.id)"
                    >
                      {{ isProcessingHermesRevision ? 'Processing...' : 'Process with Hermes' }}
                    </button>
                    <button
                      class="secondary"
                      type="button"
                      :disabled="isCreatingWriteback"
                      @click="createWritebackFromRevision(revision.id)"
                    >
                      Local Suggest
                    </button>
                    <button
                      class="secondary"
                      type="button"
                      :disabled="isCreatingProviderWriteback"
                      @click="createWritebackFromRevision(revision.id, true)"
                    >
                      Provider Suggest
                    </button>
                    <button
                      class="secondary danger"
                      type="button"
                      :disabled="isRestoringRevision"
                      @click="restoreRevision(revision.id)"
                    >
                      Restore
                    </button>
                  </div>
                </div>
              </div>
              <pre>{{ revision.content }}</pre>
            </article>
            <p v-if="manuscriptRevisions.length === 0" class="empty-state">
              No accepted revisions yet.
            </p>
          </div>
        </section>

        <section class="writeback-review">
          <div class="panel-header">
            <div>
              <p class="eyebrow">State Write-back</p>
              <h3>Canon / Memory Proposals</h3>
            </div>
            <div class="button-row">
              <span class="step-chip">{{ pendingWritebackCount }} pending</span>
              <button class="secondary" type="button" @click="loadWritebackProposals()">
                Refresh
              </button>
            </div>
          </div>

          <p v-if="writebackError" class="error">{{ writebackError }}</p>
          <p v-else-if="writebackStatus" class="save-state">{{ writebackStatus }}</p>

          <section v-if="hermesProcessReport" class="export-output">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">Hermes {{ hermesProcessReport.status }}</p>
                <h4>{{ hermesProcessReport.processed_source_ref }}</h4>
              </div>
              <span class="step-chip">{{ hermesProcessReport.wiki_changes.length }} wiki changes</span>
            </div>
            <p class="proposal-rationale">{{ hermesProcessReport.summary }}</p>
            <dl v-if="hermesProcessReport.wiki_changes.length" class="proposal-meta">
              <div v-for="change in hermesProcessReport.wiki_changes" :key="`${change.action}-${change.path}`">
                <dt>{{ change.action }}</dt>
                <dd>{{ change.path }} - {{ change.reason }}</dd>
              </div>
            </dl>
            <dl v-if="hermesProcessReport.issues.length" class="proposal-meta">
              <div v-for="issue in hermesProcessReport.issues" :key="`${issue.code}-${issue.message}`">
                <dt>{{ issue.severity }} / {{ issue.code }}</dt>
                <dd>{{ issue.message }}</dd>
              </div>
            </dl>
          </section>

          <div class="proposal-grid">
            <aside class="proposal-list" aria-label="Write-back proposals">
              <button
                v-for="proposal in writebackProposals"
                :key="proposal.id"
                :class="{ active: proposal.id === activeWritebackId }"
                type="button"
                @click="activeWritebackId = proposal.id"
              >
                <span>{{ proposal.title }}</span>
                <small>{{ proposal.target.replace('_', ' ') }} / {{ statusText(proposal.status) }}</small>
              </button>
              <p v-if="writebackProposals.length === 0" class="empty-state">
                No write-back proposals yet.
              </p>
            </aside>

            <section v-if="activeWritebackProposal" class="proposal-detail">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">{{ statusText(activeWritebackProposal.status) }}</p>
                  <h4>{{ activeWritebackProposal.title }}</h4>
                </div>
                <div class="button-row">
                  <button
                    v-if="activeWritebackProposal.status === 'pending_review'"
                    class="secondary danger"
                    type="button"
                    :disabled="isUpdatingWriteback"
                    @click="updateWritebackStatus(activeWritebackProposal.id, 'rejected')"
                  >
                    Reject
                  </button>
                  <button
                    v-if="activeWritebackProposal.status === 'pending_review'"
                    class="primary"
                    type="button"
                    :disabled="isUpdatingWriteback"
                    @click="updateWritebackStatus(activeWritebackProposal.id, 'accepted')"
                  >
                    Accept
                  </button>
                </div>
              </div>

              <dl class="proposal-meta">
                <div>
                  <dt>Target</dt>
                  <dd>{{ activeWritebackProposal.target.replace('_', ' ') }}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{{ activeWritebackProposal.source_ref || 'none' }}</dd>
                </div>
                <div>
                  <dt>Applied Record</dt>
                  <dd>{{ activeWritebackProposal.applied_record_id || 'not applied' }}</dd>
                </div>
              </dl>

              <section>
                <p class="eyebrow">Rationale</p>
                <p class="proposal-rationale">{{ activeWritebackProposal.rationale || 'No rationale recorded.' }}</p>
              </section>
              <section>
                <p class="eyebrow">Structured Payload</p>
                <pre>{{ formatJson(activeWritebackProposal.payload) }}</pre>
              </section>
            </section>
          </div>
        </section>
      </section>
    </section>
  </main>
</template>
