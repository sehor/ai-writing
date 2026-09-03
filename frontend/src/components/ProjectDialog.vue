<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useProjectsStore } from '../stores/projects'
import { useWorkspaceStore } from '../stores/workspace'

const dialog = ref<HTMLDialogElement | null>(null)
const projectsStore = useProjectsStore()
const workspace = useWorkspaceStore()
const {
  projects,
  newProject,
  isCreating,
  createError,
  createStatus,
} = storeToRefs(projectsStore)
const { activeProjectId } = storeToRefs(workspace)

function showDialog() {
  createError.value = ''
  createStatus.value = ''
  dialog.value?.showModal()
}

function closeDialog() {
  dialog.value?.close()
}

async function openProject(projectId: string) {
  activeProjectId.value = projectId
  await nextTick()
  if (activeProjectId.value === projectId) closeDialog()
}

async function submitProject() {
  const created = await projectsStore.createProject()
  await nextTick()
  if (created && activeProjectId.value === created.id) closeDialog()
}
</script>

<template>
  <button class="secondary project-dialog-trigger" type="button" @click="showDialog">
    Open project
  </button>

  <dialog ref="dialog" class="project-dialog" aria-labelledby="project-dialog-title">
    <header class="project-dialog-header">
      <div>
        <p class="eyebrow">Workspace</p>
        <h2 id="project-dialog-title">Open project</h2>
      </div>
      <button class="dialog-close" type="button" aria-label="Close project dialog" @click="closeDialog">
        &times;
      </button>
    </header>

    <div class="project-dialog-body">
      <ul v-if="projects.length" class="project-picker-list" aria-label="Available projects">
        <li v-for="project in projects" :key="project.id">
          <button
            type="button"
            :class="{ current: project.id === activeProjectId }"
            :aria-current="project.id === activeProjectId ? 'true' : undefined"
            @click="openProject(project.id)"
          >
            <span class="project-picker-copy">
              <strong>{{ project.title }}</strong>
              <small>{{ project.premise }}</small>
            </span>
            <span class="project-picker-step">Step {{ project.current_step }}</span>
          </button>
        </li>
      </ul>
      <p v-else class="empty-projects">No projects yet. Create one below.</p>

      <details class="project-create-disclosure">
        <summary>Create new project</summary>
        <form class="project-dialog-form" @submit.prevent="submitProject">
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
            <p v-if="createError" class="error" role="alert">{{ createError }}</p>
            <p v-else-if="createStatus" class="success" role="status">{{ createStatus }}</p>
            <button class="primary" type="submit" :disabled="isCreating">
              {{ isCreating ? 'Creating...' : 'Create Project' }}
            </button>
          </div>
        </form>
      </details>
    </div>
  </dialog>
</template>
