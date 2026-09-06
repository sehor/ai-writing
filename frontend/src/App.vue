<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useWorkspaceStore } from './stores/workspace'
import { useAnalysisJobsStore } from './stores/analysisJobs'
import { useProjectsStore } from './stores/projects'
import { useAppearanceStore } from './stores/appearance'
import { sections } from './services/preferences'
import AppSidebar from './components/AppSidebar.vue'
import ProjectDialog from './components/ProjectDialog.vue'
import BackupWorkspace from './components/BackupWorkspace.vue'
import AppDialog from './components/ui/AppDialog.vue'
import AppIcon from './components/ui/AppIcon.vue'
import SnowflakeWorkspace from './components/SnowflakeWorkspace.vue'
import CanonWorkspace from './components/CanonWorkspace.vue'
import MemoryWorkspace from './components/MemoryWorkspace.vue'
import GraphWorkspace from './components/GraphWorkspace.vue'
import ManuscriptWorkspace from './components/ManuscriptWorkspace.vue'
const workspace = useWorkspaceStore()
const projects = useProjectsStore()
const appearance = useAppearanceStore()
const settings = ref<InstanceType<typeof AppDialog>>()
const backup = ref<InstanceType<typeof AppDialog>>()
const currentSection = computed(
  () => sections.find((section) => section.id === workspace.activeSection)!,
)
onMounted(workspace.loadInitialData)
onBeforeUnmount(() => useAnalysisJobsStore().stop())
watch(
  () => workspace.activeSection,
  () => {
    appearance.focus = false
  },
)
</script>
<template>
  <a class="skip-link" href="#workspace-main">跳到工作区</a>
  <main class="shell" :class="{ 'focus-mode': appearance.focus }">
    <AppSidebar />
    <button
      v-if="appearance.navigationOpen"
      class="navigation-scrim"
      aria-label="收起导航"
      @click="appearance.navigationOpen = false"
    ></button>
    <section class="workspace">
      <header class="topbar">
        <div class="topbar-location">
          <button
            class="icon-button mobile-navigation"
            aria-label="打开导航"
            @click="appearance.navigationOpen = !appearance.navigationOpen"
          >
            <AppIcon name="menu" /></button
          ><ProjectDialog /><span class="breadcrumb-divider">/</span
          ><span>{{ currentSection.label }}</span>
        </div>
        <div class="topbar-actions">
          <button class="quiet-button" @click="backup?.open()">
            <AppIcon name="folder" /><span>项目备份</span></button
          ><button
            class="icon-button"
            :aria-label="
              appearance.theme === 'light' ? '切换深色主题' : '切换浅色主题'
            "
            :title="
              appearance.theme === 'light' ? '切换深色主题' : '切换浅色主题'
            "
            @click="
              appearance.theme = appearance.theme === 'light' ? 'dark' : 'light'
            "
          >
            <AppIcon
              :name="appearance.theme === 'light' ? 'moon' : 'sun'"
            /></button
          ><button
            class="icon-button"
            aria-label="工作台设置"
            title="工作台设置"
            @click="settings?.open()"
          >
            <AppIcon name="settings" />
          </button>
        </div>
      </header>
      <p v-if="projects.createStatus" class="inline-notice" role="status">
        {{ projects.createStatus }}
      </p>
      <div
        v-if="workspace.apiStatus === 'offline'"
        class="connection-notice"
        role="alert"
      >
        暂时无法连接本地服务。已输入的内容会保留，请检查服务后重试。<button
          class="quiet-button"
          @click="workspace.loadInitialData"
        >
          重新连接
        </button>
      </div>
      <div v-if="workspace.isLoadingProject" class="loading-bar" role="status">
        正在打开项目…
      </div>
      <fieldset
        id="workspace-main"
        tabindex="-1"
        class="workspace-content"
        :disabled="workspace.isLoadingProject"
        :aria-busy="workspace.isLoadingProject"
      >
        <ManuscriptWorkspace v-if="workspace.activeSection === 'manuscript'" />
        <div v-else class="module-page">
          <header class="module-heading">
            <div>
              <h1>{{ currentSection.label }}</h1>
              <p>{{ currentSection.description }}</p>
            </div>
            <span class="project-title">{{
              workspace.activeProject?.title ?? '尚未选择项目'
            }}</span>
          </header>
          <SnowflakeWorkspace
            v-if="workspace.activeSection === 'snowflake'"
          /><CanonWorkspace
            v-if="workspace.activeSection === 'canon'"
          /><MemoryWorkspace
            v-if="workspace.activeSection === 'memory'"
          /><GraphWorkspace v-if="workspace.activeSection === 'graph'" />
        </div>
      </fieldset>
    </section>
  </main>
  <AppDialog ref="backup" title="项目备份与恢复"><BackupWorkspace /></AppDialog>
  <AppDialog ref="settings" title="工作台设置">
    <section class="settings-section">
      <h3>阅读偏好</h3>
      <label
        >外观<select v-model="appearance.theme">
          <option value="light">浅色</option>
          <option value="dark">深色</option>
        </select></label
      ><label
        >正文字号<select v-model.number="appearance.fontSize">
          <option v-for="size in [16, 18, 20, 22]" :key="size" :value="size">
            {{ size }} px
          </option>
        </select></label
      >
    </section>
    <section class="settings-section">
      <h3>生成模型</h3>
      <label
        >默认模型<select v-model="workspace.selectedModelProfile">
          <option value="">自动选择 / 本地模式</option>
          <option
            v-for="profile in workspace.modelProfiles"
            :key="profile.id"
            :value="profile.id"
          >
            {{ profile.label }}{{ profile.configured ? '' : '（未配置）' }}
          </option>
        </select></label
      >
    </section>
    <section class="settings-section">
      <h3>当前项目</h3>
      <strong>{{ workspace.activeProject?.title ?? '尚未选择项目' }}</strong>
      <p>
        {{ workspace.activeProject?.premise ?? '创建项目，开始你的故事。' }}
      </p>
    </section>
    <details>
      <summary>服务与运行详情</summary>
      <p>本地服务：{{ workspace.apiStatus }}</p>
      <p>{{ workspace.runtimeLabel }}</p>
      <p>{{ workspace.runtimeTitle }}</p>
    </details>
  </AppDialog>
</template>
