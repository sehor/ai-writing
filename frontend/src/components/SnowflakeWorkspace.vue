<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import { useSnowflakeStore } from '../stores/snowflake'
import { useProjectsStore } from '../stores/projects'

const workspace = useWorkspaceStore()
const snowflake = useSnowflakeStore()
const projectsStore = useProjectsStore()
const {
  activeStepNumber,
  activeStep,
  activeProject
} = storeToRefs(workspace)
const {
  steps,
  artifacts,
  isSavingArtifact,
  isGeneratingArtifact,
  isCompilingArtifact,
  artifactError,
  artifactDraft,
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
  newProject,
  isCreating,
  createError
} = storeToRefs(projectsStore)
const {
  createProject
} = projectsStore
const {
  saveArtifact,
  generateArtifact,
  compileStepArtifact,
  toggleSceneProposalSelection,
  acceptSceneProposalBatch,
  rejectSceneProposal
} = snowflake
const {
  selectStep
} = workspace

const compilerStep = computed(() => {
  const number = activeStep.value?.number ?? 0
  if (number === 7) return 'canon' as const
  if (number === 8) return 'scene' as const
  return null
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
</script>

<template>
<section
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

      <section class="pipeline">
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
              :disabled="isCompilingArtifact || !activeProject || !artifactDraft.trim()"
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
                    :disabled="proposal.status !== 'pending_review'"
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
                  <span v-if="proposal.warnings.length" class="warning-count" :title="proposal.warnings.join('\n')">
                    {{ proposal.warnings.length }}
                  </span>
                  <span v-else>-</span>
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
                !sceneProposals.some((proposal) => proposal.status === 'pending_review')
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

<style scoped>
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

.batch-actions {
  justify-content: flex-start;
}
</style>
