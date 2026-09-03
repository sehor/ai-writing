<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import { useSnowflakeStore } from '../stores/snowflake'
import { useManuscriptStore } from '../stores/manuscript'
import SnowflakeRevisionHistory from './snowflake/SnowflakeRevisionHistory.vue'
import SnowflakeRecords from './snowflake/SnowflakeRecords.vue'

const workspace = useWorkspaceStore()
const snowflake = useSnowflakeStore()
const manuscript = useManuscriptStore()
const {
  activeStepNumber,
  activeStep,
  activeProject
} = storeToRefs(workspace)
const {
  steps,
  stepStates,
  isSavingArtifact,
  isGeneratingArtifact,
  isCompilingArtifact,
  artifactError,
  artifactDraft,
  generationInstruction,
  generationMode,
  previousArtifactsContextChars,
  activeRevision,
  revisions,
  activeStepState,
  manuscriptProgress,
  workflowTrace,
  hasUnsavedArtifactChanges,
  artifactStateLabel,
  sceneProposals,
  canonExtractionReport,
  sceneParseReport,
  selectedSceneProposalIds,
  sceneProposalError,
  sceneProposalStatus
} = storeToRefs(snowflake)
const {
  saveArtifact,
  generateArtifact,
  decideRevision,
  skipActiveStep,
  compileStepArtifact,
  toggleSceneProposalSelection,
  acceptSceneProposalBatch,
  rejectSceneProposal
} = snowflake
const { sceneContracts } = storeToRefs(manuscript)
const {
  selectStep
} = workspace

const isStepWorkspaceOpen = ref(false)
const legacySource = ref<HTMLTextAreaElement | null>(null)
const legacyImportSceneId = ref('')
const legacyImportTitle = ref('')
const legacyImportContent = ref('')
const legacyImportError = ref('')
const legacyImportStatus = ref('')
const isImportingLegacy = ref(false)

function openStep(stepNumber: number) {
  selectStep(stepNumber)
  isStepWorkspaceOpen.value = true
}

watch(
  () => [activeProject.value?.id, activeStepNumber.value],
  ([projectId, stepNumber]) => {
    if (projectId && stepNumber === 10) void manuscript.refreshSceneContracts(String(projectId))
  },
  { immediate: true },
)

function captureLegacySelection() {
  const source = legacySource.value
  if (!source || source.selectionStart === source.selectionEnd) return
  legacyImportContent.value = source.value.slice(source.selectionStart, source.selectionEnd).trim()
  legacyImportError.value = ''
  legacyImportStatus.value = 'Selection captured. Choose its Scene Contract and import it for review.'
}

function updateLegacyImportTitle() {
  const scene = sceneContracts.value.find((item) => item.id === legacyImportSceneId.value)
  if (scene) legacyImportTitle.value = scene.title
}

async function importLegacySelection() {
  if (!legacyStep10Revision.value) return
  legacyImportError.value = ''
  legacyImportStatus.value = ''
  isImportingLegacy.value = true
  try {
    await snowflake.importLegacyDraftSelection(
      legacyStep10Revision.value.id,
      legacyImportSceneId.value,
      legacyImportTitle.value,
      legacyImportContent.value,
    )
    legacyImportStatus.value = 'Pending Manuscript proposal created. Open Manuscript to review it.'
    legacyImportContent.value = ''
  } catch (error) {
    legacyImportError.value = error instanceof Error ? error.message : 'Could not import selection.'
  } finally {
    isImportingLegacy.value = false
  }
}

function moveStep(offset: number) {
  const nextStep = steps.value.find((step) => step.number === activeStepNumber.value + offset)
  if (nextStep) selectStep(nextStep.number)
}

const compilerStep = computed(() => {
  const number = activeStep.value?.number ?? 0
  if (number === 7) return 'canon' as const
  if (number === 8) return 'scene' as const
  return null
})
const isRecordStep = computed(
  () => activeStepNumber.value >= 6 && activeStepNumber.value <= 9
)
const legacyStep10Revision = computed(() =>
  revisions.value.find((revision) => revision.status === 'legacy_draft')
)
const acceptanceImpact = computed(() => {
  const affected = new Set<number>([activeStepNumber.value])
  let changed = true
  while (changed) {
    changed = false
    for (const step of steps.value) {
      if (!affected.has(step.number) && step.dependencies.some((dependency) => affected.has(dependency))) {
        affected.add(step.number)
        changed = true
      }
    }
  }
  affected.delete(activeStepNumber.value)
  return [...affected].sort((left, right) => left - right)
})

const canonCreateCount = computed(
  () => canonExtractionReport.value?.proposals.filter((proposal) => proposal.action === 'create').length ?? 0
)
const canonUpdateCount = computed(
  () => canonExtractionReport.value?.proposals.filter((proposal) => proposal.action === 'update').length ?? 0
)

function statusLabel(status: string): string {
  if (status === 'pending_review') return 'Pending review'
  if (status === 'accepted') return 'Accepted'
  if (status === 'rejected') return 'Rejected'
  return 'Superseded'
}

function stateFor(stepNumber: number) {
  return stepStates.value.find((item) => item.step.number === stepNumber)
}

function stepStateLabel(stepNumber: number): string {
  const state = stateFor(stepNumber)
  if (!state) return 'Missing'
  if (state.pending_count > 0) return `${state.pending_count} pending`
  if (state.state === 'approved') return 'Approved'
  if (state.state === 'stale') return 'Needs review'
  if (state.state === 'skipped') return 'Skipped'
  return 'Missing'
}

function openManuscript() {
  workspace.activeSection = 'manuscript'
}
</script>

<template>
      <section v-if="!isStepWorkspaceOpen" class="pipeline">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Compiler Pipeline</p>
            <h3>Snowflake Method</h3>
          </div>
          <span class="step-chip">
            {{ stepStates.filter((item) => item.state === 'approved').length }} approved
          </span>
        </div>

        <ol class="steps">
          <li
            v-for="step in steps"
            :key="step.number"
            :class="{
              current: step.number === activeStepNumber,
              saved: stateFor(step.number)?.state === 'approved',
              stale: stateFor(step.number)?.state === 'stale',
              pending: (stateFor(step.number)?.pending_count ?? 0) > 0,
            }"
          >
            <button
              class="step-selector"
              type="button"
              :aria-label="`Open step ${step.number}: ${step.title}`"
              :aria-current="step.number === activeStepNumber ? 'step' : undefined"
              @click="openStep(step.number)"
            >
              <span class="step-number">{{ step.number }}</span>
              <span class="step-copy">
                <span class="step-heading">
                  <strong>{{ step.title }}</strong>
                  <span
                    :class="stateFor(step.number)?.state === 'approved' ? 'selected-step-label' : 'open-step-label'"
                  >{{ stepStateLabel(step.number) }}</span>
                </span>
                <span>{{ step.description }}</span>
                <code>{{ step.artifact }}</code>
              </span>
            </button>
          </li>
        </ol>
      </section>

      <template v-else>
      <section class="step-workspace-header" aria-labelledby="step-workspace-title">
        <button class="secondary back-to-steps" type="button" @click="isStepWorkspaceOpen = false">
          &larr; All Snowflake steps
        </button>
        <div class="step-workspace-title">
          <p class="eyebrow">Snowflake Method &middot; Step {{ activeStepNumber }} of {{ steps.length }}</p>
          <h3 id="step-workspace-title">{{ activeStep?.title ?? 'Snowflake Step' }}</h3>
          <p>{{ activeStep?.description }}</p>
        </div>
        <div class="step-navigation" aria-label="Step navigation">
          <button
            class="secondary"
            type="button"
            :disabled="activeStepNumber <= 1"
            @click="moveStep(-1)"
          >
            Previous
          </button>
          <button
            class="secondary"
            type="button"
            :disabled="activeStepNumber >= steps.length"
            @click="moveStep(1)"
          >
            Next
          </button>
        </div>
      </section>

      <section
        v-if="activeStep?.virtual"
        class="artifact-editor manuscript-milestone"
        aria-labelledby="manuscript-milestone-title"
      >
        <div>
          <p class="eyebrow">Virtual milestone</p>
          <h3 id="manuscript-milestone-title">Draft through the Manuscript workflow</h3>
          <p>
            Step 10 no longer creates a second full-manuscript artifact. Draft each accepted
            Scene Contract as a proposal, review it, and commit it as a Manuscript revision.
          </p>
          <dl v-if="manuscriptProgress" class="milestone-stats">
            <div><dt>Scene Contracts</dt><dd>{{ manuscriptProgress.total_scene_contracts }}</dd></div>
            <div><dt>Pending proposals</dt><dd>{{ manuscriptProgress.pending_manuscript_proposals }}</dd></div>
            <div><dt>Accepted revisions</dt><dd>{{ manuscriptProgress.accepted_latest_revisions }}</dd></div>
            <div><dt>Stale scenes</dt><dd>{{ manuscriptProgress.stale_scene_count }}</dd></div>
            <div><dt>Completion</dt><dd>{{ manuscriptProgress.completion_percent }}%</dd></div>
          </dl>
          <details v-if="legacyStep10Revision" class="legacy-manuscript">
            <summary>Legacy Step 10 draft · read-only</summary>
            <p>
              This historical draft is preserved but is not approved. Select text below, then
              import it into a Scene Contract as a pending Manuscript proposal.
            </p>
            <textarea
              ref="legacySource"
              :value="legacyStep10Revision.content"
              rows="10"
              readonly
              aria-label="Preserved legacy Step 10 draft"
              @select="captureLegacySelection"
            />
            <div class="legacy-import-form">
              <label>
                <span>Target Scene Contract</span>
                <select v-model="legacyImportSceneId" @change="updateLegacyImportTitle">
                  <option value="">Choose a scene</option>
                  <option v-for="scene in sceneContracts" :key="scene.id" :value="scene.id">
                    {{ scene.sequence }}. {{ scene.title }}
                  </option>
                </select>
              </label>
              <label>
                <span>Proposal title</span>
                <input v-model="legacyImportTitle" maxlength="160" />
              </label>
              <label>
                <span>Selected legacy text</span>
                <textarea v-model="legacyImportContent" rows="6" readonly />
              </label>
              <p v-if="legacyImportError" class="error">{{ legacyImportError }}</p>
              <p v-else-if="legacyImportStatus" class="save-state">{{ legacyImportStatus }}</p>
              <button
                class="secondary"
                type="button"
                :disabled="
                  isImportingLegacy ||
                  !legacyImportSceneId ||
                  !legacyImportTitle.trim() ||
                  !legacyImportContent
                "
                @click="importLegacySelection"
              >
                {{ isImportingLegacy ? 'Importing...' : 'Import selection for review' }}
              </button>
            </div>
          </details>
        </div>
        <button class="primary" type="button" @click="openManuscript">Open Manuscript workspace</button>
      </section>

      <section
        v-else
        class="artifact-editor"
        aria-labelledby="artifact-editor-title"
      >
        <div class="panel-header">
          <div>
            <p class="eyebrow">{{ isRecordStep ? 'Authoritative records' : 'Active Artifact' }}</p>
            <h3 id="artifact-editor-title">
              Step {{ activeStep?.number ?? 1 }}: {{ activeStep?.title ?? 'Snowflake Step' }}
            </h3>
          </div>
          <span class="step-chip">{{ activeStep?.artifact ?? 'artifact' }}</span>
        </div>

        <textarea
          v-if="!isRecordStep"
          v-model="artifactDraft"
          rows="12"
          :disabled="!activeProject"
          :placeholder="`Write the ${activeStep?.artifact ?? 'artifact'} for the active project.`"
        />

        <details
          v-if="
            isRecordStep &&
            activeStepState?.accepted_revision &&
            activeStepState.accepted_revision.source !== 'derived'
          "
          class="legacy-manuscript"
        >
          <summary>Preserved legacy Artifact — reference only</summary>
          <p>
            This historical blob is not an authoritative Step {{ activeStepNumber }} head.
            Convert the useful material into records below and accept those records before compiling.
          </p>
          <textarea
            :value="activeStepState.accepted_revision.content"
            rows="8"
            readonly
            aria-label="Preserved legacy Snowflake Artifact"
          />
        </details>

        <div class="generation-controls">
          <label class="generation-instruction">
            <span>AI instruction</span>
            <textarea
              v-model="generationInstruction"
              rows="3"
              maxlength="4000"
              :disabled="!activeProject"
              :placeholder="
                isRecordStep
                  ? 'Describe which record proposals to generate or revise.'
                  : 'Describe what to generate or revise. The current artifact is kept separate.'
              "
            />
          </label>

          <label class="context-budget">
            <span>Upstream context budget</span>
            <input
              v-model.number="previousArtifactsContextChars"
              type="number"
              min="1000"
              max="400000"
              step="1000"
              inputmode="numeric"
              :disabled="!activeProject"
              aria-describedby="snowflake-context-budget-help"
            />
            <small id="snowflake-context-budget-help">
              Relevant accepted upstream records are ranked first; early-step artifacts use the remaining budget.
            </small>
          </label>

          <label class="generation-mode">
            <span>Generation mode</span>
            <select v-model="generationMode" :disabled="!activeProject">
              <template v-if="isRecordStep">
                <option value="record_set">Generate record drafts</option>
                <option value="selection">Revise selected accepted records</option>
                <option value="continue">Continue selected accepted records</option>
              </template>
              <option v-else value="replace">Generate artifact revision</option>
            </select>
            <small v-if="isRecordStep">
              New and targeted results always become pending record revisions. Blob Artifact revisions are not created.
            </small>
          </label>
        </div>

        <div class="form-actions artifact-actions">
          <p v-if="artifactError" class="error">{{ artifactError }}</p>
          <p v-else class="save-state">
            {{ isRecordStep ? 'Accept record revisions below to update the derived step projection.' : artifactStateLabel }}
          </p>
          <p
            v-if="!isRecordStep && activeRevision && ['draft', 'pending_review'].includes(activeRevision.status) && acceptanceImpact.length"
            class="save-state"
          >
            Accepting this revision will mark downstream steps {{ acceptanceImpact.join(', ') }} for review.
          </p>
          <div class="button-row">
            <button
              class="secondary"
              type="button"
              :disabled="isGeneratingArtifact || !activeProject"
              @click="generateArtifact"
            >
              {{ isGeneratingArtifact ? 'Generating...' : isRecordStep ? 'Generate record proposals' : 'Generate Proposal' }}
            </button>
            <button
              v-if="!isRecordStep"
              class="primary"
              type="button"
              :disabled="isSavingArtifact || !hasUnsavedArtifactChanges"
              @click="saveArtifact"
            >
              {{ isSavingArtifact ? 'Saving...' : 'Save Draft Revision' }}
            </button>
            <button
              v-if="!isRecordStep && activeRevision && ['draft', 'pending_review'].includes(activeRevision.status)"
              class="primary"
              type="button"
              :disabled="isSavingArtifact || hasUnsavedArtifactChanges"
              @click="decideRevision(activeRevision.id, 'accepted')"
            >
              Accept revision
            </button>
            <button
              v-if="!isRecordStep && activeRevision && ['draft', 'pending_review'].includes(activeRevision.status)"
              class="secondary"
              type="button"
              :disabled="isSavingArtifact"
              @click="decideRevision(activeRevision.id, 'rejected')"
            >
              Reject
            </button>
            <button
              v-if="activeStep?.optional && activeStepState?.state !== 'skipped'"
              class="secondary"
              type="button"
              :disabled="isSavingArtifact"
              @click="skipActiveStep"
            >
              Skip optional step
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

      <SnowflakeRevisionHistory v-if="!activeStep?.virtual && !isRecordStep" :key="activeStepNumber" />
      <SnowflakeRecords
        v-if="activeStepNumber >= 6 && activeStepNumber <= 9"
        :key="`records-${activeStepNumber}`"
      />

      <section
        v-if="compilerStep"
        class="compile-panel"
        aria-labelledby="compile-panel-title"
      >
        <div class="panel-header">
          <div>
            <p class="eyebrow">Structured Compiler</p>
            <h3 id="compile-panel-title">
              {{
                compilerStep === 'canon'
                  ? 'Step 7: Compile into Canon Proposals'
                  : 'Step 8: Parse into Scene Proposals'
              }}
            </h3>
          </div>
          <span v-if="compilerStep === 'canon' && canonExtractionReport" class="step-chip">
            {{ canonExtractionReport.cached ? 'cached' : 'run' }} v{{ canonExtractionReport.run_version }}
          </span>
          <span v-else-if="compilerStep === 'scene' && sceneParseReport" class="step-chip">
            {{ sceneParseReport.cached ? 'cached' : 'run' }} v{{ sceneParseReport.run_version }}
          </span>
        </div>

        <p class="compile-hint">
          {{
            compilerStep === 'canon'
              ? 'Compiles accepted Character Bible records into Canon create / update proposals. Draft and rejected records are ignored; nothing is written to Canon until you accept each proposal.'
              : 'Compiles accepted Scene List records into structured Scene Contract proposals. Draft and rejected records are ignored; blocking contract findings stop compilation.'
          }}
        </p>

        <div class="form-actions artifact-actions">
          <p v-if="sceneProposalError" class="error">{{ sceneProposalError }}</p>
          <p v-else-if="sceneProposalStatus" class="save-state">{{ sceneProposalStatus }}</p>
          <div class="button-row">
            <button
              class="primary"
              type="button"
              :disabled="
                isCompilingArtifact ||
                !activeProject ||
                activeStepState?.state !== 'approved'
              "
              @click="compileStepArtifact"
            >
              {{
                isCompilingArtifact
                  ? 'Compiling...'
                  : compilerStep === 'canon'
                    ? 'Extract Canon Proposals'
                    : 'Parse Scene Proposals'
              }}
            </button>
          </div>
        </div>

        <template v-if="compilerStep === 'canon' && canonExtractionReport">
          <p v-if="canonExtractionReport.proposals.length" class="compile-summary">
            {{ canonExtractionReport.proposals.length }} proposal(s):
            {{ canonCreateCount }} create, {{ canonUpdateCount }} update.
            Review and accept them under Manuscript &gt; Write-backs.
          </p>
          <p v-else class="save-state">
            No new Canon proposals from the accepted records (Canon may already match).
          </p>
          <ul v-if="canonExtractionReport.warnings.length" class="warning-list">
            <li v-for="(warning, index) in canonExtractionReport.warnings" :key="index">
              {{ warning }}
            </li>
          </ul>
        </template>

        <template v-if="compilerStep === 'scene' && sceneProposals.length">
          <table class="scene-proposal-table">
            <thead>
              <tr>
                <th scope="col"></th>
                <th scope="col">#</th>
                <th scope="col">Title</th>
                <th scope="col">POV</th>
                <th scope="col">Goal</th>
                <th scope="col">Warnings</th>
                <th scope="col">Status</th>
                <th scope="col"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="proposal in sceneProposals"
                :key="proposal.id"
                :class="{ decided: proposal.status !== 'pending_review' }"
              >
                <td>
                  <input
                    type="checkbox"
                    :checked="selectedSceneProposalIds.includes(proposal.id)"
                    :disabled="
                      proposal.status !== 'pending_review' || proposal.blocking_errors.length > 0
                    "
                    :aria-label="`Select scene proposal ${proposal.sequence}`"
                    @change="toggleSceneProposalSelection(proposal.id)"
                  />
                </td>
                <td>{{ proposal.sequence }}</td>
                <td>
                  {{ proposal.title }}
                  <small v-if="proposal.chapter_hint" class="muted">({{ proposal.chapter_hint }})</small>
                </td>
                <td>{{ proposal.pov || '-' }}</td>
                <td class="goal-cell">{{ proposal.goal || '-' }}</td>
                <td>
                  <span
                    v-if="proposal.blocking_errors.length"
                    class="blocking-count"
                    :title="proposal.blocking_errors.join('\n')"
                  >
                    Blocked ({{ proposal.blocking_errors.length }})
                  </span>
                  <span v-if="proposal.warnings.length" class="warning-count" :title="proposal.warnings.join('\n')">
                    {{ proposal.warnings.length }}
                  </span>
                  <span v-else-if="!proposal.blocking_errors.length">-</span>
                </td>
                <td><span class="step-chip">{{ statusLabel(proposal.status) }}</span></td>
                <td>
                  <button
                    v-if="proposal.status === 'pending_review'"
                    class="secondary"
                    type="button"
                    @click="rejectSceneProposal(proposal.id)"
                  >
                    Reject
                  </button>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="button-row batch-actions">
            <button
              class="secondary"
              type="button"
              :disabled="
                isCompilingArtifact ||
                !selectedSceneProposalIds.length ||
                !sceneProposals.some(
                  (proposal) =>
                    proposal.status === 'pending_review' &&
                    proposal.blocking_errors.length === 0 &&
                    selectedSceneProposalIds.includes(proposal.id)
                )
              "
              @click="acceptSceneProposalBatch(false)"
            >
              Accept Selected ({{ selectedSceneProposalIds.length }})
            </button>
            <button
              class="primary"
              type="button"
              :disabled="
                isCompilingArtifact ||
                !sceneProposals.some(
                  (proposal) =>
                    proposal.status === 'pending_review' && proposal.blocking_errors.length === 0
                )
              "
              @click="acceptSceneProposalBatch(true)"
            >
              Accept All Pending
            </button>
          </div>
        </template>
        <p
          v-else-if="compilerStep === 'scene'"
          class="save-state"
        >
          No scene proposals yet. Accept Step 8 records, then compile them.
        </p>
      </section>
      </template>
</template>

<style scoped>
.steps li.stale {
  border-color: #b45309;
  box-shadow: inset 3px 0 0 #b45309;
}

.steps li.pending {
  border-style: dashed;
}

.generation-instruction {
  display: grid;
  gap: 0.5rem;
  font-weight: 600;
}

.generation-instruction textarea {
  min-height: 5rem;
  font-weight: 400;
}

.generation-controls {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(16rem, 20rem);
  gap: 1rem;
  align-items: start;
}

.context-budget small {
  color: var(--text-muted, #6b7280);
  font-weight: 400;
  line-height: 1.4;
}

@media (max-width: 760px) {
  .generation-controls {
    grid-template-columns: 1fr;
  }
}

.manuscript-milestone {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
}

.milestone-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  margin: 1rem 0 0;
}

.milestone-stats div {
  display: grid;
  gap: 0.25rem;
}

.milestone-stats dt {
  color: var(--text-muted, #6b7280);
  font-size: 0.8rem;
}

.milestone-stats dd {
  margin: 0;
  font-weight: 700;
}

.compile-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.compile-hint {
  margin: 0;
  color: var(--text-muted, #6b7280);
}

.legacy-import-form {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.compile-summary {
  margin: 0;
}

.warning-list {
  margin: 0;
  padding-left: 1.25rem;
  color: #b45309;
  font-size: 0.85rem;
}

.warning-list li + li {
  margin-top: 0.25rem;
}

.scene-proposal-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.scene-proposal-table th,
.scene-proposal-table td {
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border-muted, #e5e7eb);
  padding: 0.4rem 0.5rem;
}

.scene-proposal-table tr.decided {
  opacity: 0.6;
}

.goal-cell {
  max-width: 22rem;
  overflow-wrap: anywhere;
}

.muted {
  color: var(--text-muted, #6b7280);
}

.warning-count {
  background: #fef3c7;
  color: #92400e;
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  font-weight: 600;
  cursor: help;
}

.blocking-count {
  display: inline-block;
  margin-right: 0.25rem;
  padding: 0.05rem 0.5rem;
  border: 1px solid #b91c1c;
  color: #991b1b;
  font-weight: 700;
}

.batch-actions {
  justify-content: flex-start;
}

@media (max-width: 48rem) {
  .manuscript-milestone {
    grid-template-columns: 1fr;
    align-items: stretch;
  }
}
</style>
