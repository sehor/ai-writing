<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'
import { useBackupsStore } from '../stores/backups'

const workspace = useWorkspaceStore()
const { activeProjectId } = storeToRefs(workspace)
const backups = useBackupsStore()
const {
  preview: backupPreview,
  isExporting,
  exportError,
  importFileName,
  isLoadingPreview,
  isImporting,
  importError,
  importStatus,
  overwriteConfirmed,
} = storeToRefs(backups)

function onImportFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    backups.previewImportPackage(file)
  }
  // Reset so picking the same file again still fires change.
  input.value = ''
}

function rowCountSummary(counts: Record<string, number>): string {
  const entries = Object.entries(counts)
  if (!entries.length) return '0 rows'
  return entries.map(([table, count]) => `${table} ${count}`).join(' · ')
}
</script>

<template>
  <section class="backup-panel" aria-label="Backup and restore">
    <p class="section-label">备份 / 恢复</p>
    <button
      type="button"
      data-testid="export-backup"
      :disabled="!activeProjectId || isExporting"
      @click="backups.exportActiveProjectBackup()"
    >
      {{ isExporting ? '导出中...' : '导出项目包' }}
    </button>

    <label class="backup-import">
      <span>导入项目包</span>
      <input
        type="file"
        accept=".zip,application/zip,application/octet-stream"
        :disabled="isLoadingPreview || isImporting"
        @change="onImportFileChange"
      />
    </label>

    <div v-if="backupPreview" class="backup-preview">
      <p class="backup-preview-title">
        {{ backupPreview.project.title }}
        <small>{{ backupPreview.project.id }}</small>
      </p>
      <p class="backup-preview-meta">
        备份 v{{ backupPreview.format_version }} · schema v{{
          backupPreview.schema_version
        }}
        · {{ backupPreview.module_file_count }} 个模块文件
      </p>
      <p class="backup-preview-meta">
        {{ rowCountSummary(backupPreview.project.row_counts) }}
      </p>
      <p
        v-for="warning in backupPreview.warnings"
        :key="warning"
        class="conflict-warning"
        role="alert"
      >
        {{ warning }}
      </p>
      <p
        v-if="backupPreview.target_exists"
        class="conflict-warning"
        role="alert"
      >
        目标项目已存在：导入将覆盖现有项目，请先确认覆盖。
      </p>
      <label
        v-if="backupPreview.target_exists && backupPreview.can_overwrite"
        class="backup-overwrite-confirm"
      >
        <input v-model="overwriteConfirmed" type="checkbox" />
        <span>确认覆盖现有项目</span>
      </label>
      <div class="backup-preview-actions">
        <button
          type="button"
          data-testid="confirm-import"
          :disabled="
            isImporting ||
            (backupPreview.target_exists &&
              (!backupPreview.can_overwrite || !overwriteConfirmed))
          "
          @click="backups.importPreviewedPackage()"
        >
          {{
            isImporting
              ? '导入中...'
              : backupPreview.target_exists
                ? '覆盖并导入'
                : '确认导入'
          }}
        </button>
        <button
          type="button"
          class="secondary"
          :disabled="isImporting"
          @click="backups.discardPreview()"
        >
          取消
        </button>
      </div>
    </div>

    <p v-if="isLoadingPreview" class="backup-note">
      正在解析 {{ importFileName }} ...
    </p>
    <p v-if="importStatus" class="backup-status">{{ importStatus }}</p>
    <p v-if="exportError || importError" class="backup-error">
      {{ exportError || importError }}
    </p>
  </section>
</template>
