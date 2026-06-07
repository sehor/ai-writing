<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'

const store = useWorkspaceStore()
const {
  steps,
  artifacts,
  activeStepNumber,
  isCreating,
  isSavingArtifact,
  isGeneratingArtifact,
  createError,
  artifactError,
  artifactDraft,
  workflowTrace,
  newProject,
  activeProject,
  activeStep,
  hasUnsavedArtifactChanges,
  artifactStateLabel
} = storeToRefs(store)
const {
  createProject,
  selectStep,
  saveArtifact,
  generateArtifact
} = store
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
</template>
