<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import { useSnowflakeStore } from '../stores/snowflake'
import SnowflakeRevisionHistory from './snowflake/SnowflakeRevisionHistory.vue'
import SnowflakeRecords from './snowflake/SnowflakeRecords.vue'

const workspace = useWorkspaceStore()
const snowflake = useSnowflakeStore()
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
const {
  selectStep
} = workspace

const isStepWorkspaceOpen = ref(false)

function openStep(stepNumber: number) {
  selectStep(stepNumber)
  isStepWorkspaceOpen.value = true
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
            <p>This historical draft is preserved but is not an approved Manuscript revision.</p>
            <pre>{{ legacyStep10Revision.content }}</pre>
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

        <label class="generation-instruction">
          <span>AI instruction</span>
          <textarea
            v-model="generationInstruction"
            rows="3"
            maxlength="4000"
            :disabled="!activeProject"
            placeholder="Describe what to generate or revise. The current artifact is kept separate."
          />
        </label>

        <div class="form-actions artifact-actions">
          <p v-if="artifactError" class="error">{{ artifactError }}</p>
          <p v-else class="save-state">{{ artifactStateLabel }}</p>
          <p
            v-if="activeRevision && ['draft', 'pending_review'].includes(activeRevision.status) && acceptanceImpact.length"
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
              {{ isGeneratingArtifact ? 'Generating...' : 'Generate Proposal' }}
            </button>
            <button
              class="primary"
              type="button"
              :disabled="isSavingArtifact || !hasUnsavedArtifactChanges"
              @click="saveArtifact"
            >
              {{ isSavingArtifact ? 'Saving...' : 'Save Draft Revision' }}
            </button>
            <button
              v-if="activeRevision && ['draft', 'pending_review'].includes(activeRevision.status)"
              class="primary"
              type="button"
              :disabled="isSavingArtifact || hasUnsavedArtifactChanges"
              @click="decideRevision(activeRevision.id, 'accepted')"
            >
              Accept revision
            </button>
            <button
              v-if="activeRevision && ['draft', 'pending_review'].includes(activeRevision.status)"
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

      <SnowflakeRevisionHistory v-if="!activeStep?.virtual" :key="activeStepNumber" />
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
              ? 'Parses the saved character bible into Canon create / update proposals. Nothing is written to Canon until you accept each proposal.'
              : 'Parses the saved scene list into structured Scene Contract proposals with parse warnings. Accept a batch to create the contracts in one transaction.'
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
            No new Canon proposals from this artifact (existing records may already match).
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
          No scene proposals yet. Save the Step 8 artifact, then parse it.
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
