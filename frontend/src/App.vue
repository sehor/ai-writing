<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

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

const projects = ref<ProjectSummary[]>([])
const steps = ref<SnowflakeStep[]>([])
const activeProjectId = ref('')
const apiStatus = ref('checking')
const isCreating = ref(false)
const createError = ref('')
const newProject = ref({
  title: '',
  premise: '',
})

const activeProject = computed(() =>
  projects.value.find((project) => project.id === activeProjectId.value) ?? projects.value[0]
)

onMounted(async () => {
  try {
    const [healthResponse, projectsResponse, stepsResponse] = await Promise.all([
      fetch('/api/health'),
      fetch('/api/projects'),
      fetch('/api/snowflake/steps'),
    ])
    const health = await healthResponse.json()
    projects.value = await projectsResponse.json()
    steps.value = await stepsResponse.json()
    activeProjectId.value = projects.value[0]?.id ?? ''
    apiStatus.value = health.status
  } catch {
    apiStatus.value = 'offline'
  }
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
        <button class="active">Snowflake</button>
        <button disabled>Canon</button>
        <button disabled>Memory</button>
        <button disabled>Graph</button>
        <button disabled>Manuscript</button>
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
        <span class="status" :class="{ offline: apiStatus !== 'ok' }">
          API {{ apiStatus }}
        </span>
      </header>

      <section class="create-project" aria-labelledby="create-project-title">
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
            :class="{ current: step.number === (activeProject?.current_step ?? 1) }"
          >
            <span class="step-number">{{ step.number }}</span>
            <div>
              <h4>{{ step.title }}</h4>
              <p>{{ step.description }}</p>
              <code>{{ step.artifact }}</code>
            </div>
          </li>
        </ol>
      </section>
    </section>
  </main>
</template>
