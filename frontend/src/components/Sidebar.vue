<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'

const store = useWorkspaceStore()
const {
  projects,
  activeProjectId,
  activeSection
} = storeToRefs(store)
</script>

<template>
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
</template>
