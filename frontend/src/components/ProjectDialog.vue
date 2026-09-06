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
    {{ workspace.activeProject?.title ?? '打开项目' }}
  </button>

  <dialog ref="dialog" class="project-dialog" aria-labelledby="project-dialog-title">
    <header class="project-dialog-header">
      <div>
        <h2 id="project-dialog-title">打开项目</h2>
      </div>
      <button class="dialog-close" type="button" aria-label="关闭项目选择" @click="closeDialog">
        &times;
      </button>
    </header>

    <div class="project-dialog-body">
      <ul v-if="projects.length" class="project-picker-list" aria-label="可用项目">
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
            <span class="project-picker-step">第 {{ project.current_step }} 步</span>
          </button>
        </li>
      </ul>
      <p v-else class="empty-projects">还没有项目。在下方创建你的第一个故事。</p>

      <details class="project-create-disclosure">
        <summary>创建新项目</summary>
        <form class="project-dialog-form" @submit.prevent="submitProject">
          <label>
            <span>标题</span>
            <input v-model="newProject.title" autocomplete="off" placeholder="玻璃之城" />
          </label>
          <label>
            <span>故事梗概</span>
            <textarea
              v-model="newProject.premise"
              rows="3"
              placeholder="用一两句话描述故事的主角、困境和核心变化。"
            />
          </label>
          <div class="form-actions">
            <p v-if="createError" class="error" role="alert">{{ createError }}</p>
            <p v-else-if="createStatus" class="success" role="status">{{ createStatus }}</p>
            <button class="primary" type="submit" :disabled="isCreating">
              {{ isCreating ? '创建中…' : '创建项目' }}
            </button>
          </div>
        </form>
      </details>
    </div>
  </dialog>
</template>
