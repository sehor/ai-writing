<script setup lang="ts">
import { useWorkspaceStore } from '../stores/workspace'
import { useAppearanceStore } from '../stores/appearance'
import { sections } from '../services/preferences'
import AppIcon from './ui/AppIcon.vue'
import type { ActiveSection } from '../types'
const workspace = useWorkspaceStore()
const appearance = useAppearanceStore()
function selectSection(section: ActiveSection) {
  workspace.activeSection = section
  appearance.navigationOpen = false
}
</script>
<template>
  <aside
    class="sidebar"
    :class="{ 'navigation-open': appearance.navigationOpen }"
    aria-label="工作区导航"
  >
    <a class="brand" href="#workspace-main"
      ><span class="brand-mark"><AppIcon name="feather" :size="25" /></span
      ><span class="brand-copy"
        ><strong>AI Writing</strong><small>Studio · 长篇创作</small></span
      ></a
    >
    <p class="nav-caption">创作空间</p>
    <nav class="nav" aria-label="创作模块">
      <button
        v-for="section in sections"
        :key="section.id"
        type="button"
        :class="{ active: workspace.activeSection === section.id }"
        :aria-current="
          workspace.activeSection === section.id ? 'page' : undefined
        "
        :title="section.label"
        @click="selectSection(section.id)"
      >
        <AppIcon :name="section.icon" /><span>{{ section.label }}</span>
      </button>
    </nav>
    <div class="sidebar-foot">
      <span class="local-dot"></span><span>本地创作 · 由你掌握</span>
    </div>
  </aside>
</template>
