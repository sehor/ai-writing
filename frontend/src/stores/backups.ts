import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchApi } from '../api/client'
import { readErrorDetail } from '../api/errors'
import type { BackupImportSummary, BackupPreviewSummary } from '../types'
import { useProjectsStore } from './projects'
import { useWorkspaceStore } from './workspace'
import type { WorkspaceShell } from './workspaceShell'

/** Project backup / restore (P2-07 frontend): download the ZIP package of the
 *  active project, preview an uploaded package before importing, and restore
 *  it with an explicit overwrite confirmation when the target already exists. */
export const useBackupsStore = defineStore('backups', () => {
  // Lazy, explicitly-typed access keeps the store type graph acyclic.
  function ws(): WorkspaceShell {
    return useWorkspaceStore()
  }

  const isExporting = ref(false)
  const exportError = ref('')
  const importFileName = ref('')
  const preview = ref<BackupPreviewSummary | null>(null)
  const isLoadingPreview = ref(false)
  const isImporting = ref(false)
  const importError = ref('')
  const importStatus = ref('')
  const overwriteConfirmed = ref(false)

  /** The selected package file; kept outside reactivity on purpose. */
  let pendingPackage: File | null = null
  let previewController: AbortController | undefined
  let previewVersion = 0

  function resetPreviewState() {
    previewController?.abort()
    previewVersion++
    isLoadingPreview.value = false
    pendingPackage = null
    importFileName.value = ''
    preview.value = null
    overwriteConfirmed.value = false
  }

  /** Download the active project's ZIP package through a temporary object URL. */
  async function exportActiveProjectBackup() {
    exportError.value = ''
    const projectId = ws().activeProject?.id
    if (!projectId) {
      exportError.value = 'Create or select a project first.'
      return
    }

    isExporting.value = true
    try {
      const response = await fetchApi(`/projects/${projectId}/backup`)
      if (!response.ok) {
        throw new Error(`Backup request failed: ${response.status}`)
      }
      const disposition = response.headers.get('Content-Disposition') ?? ''
      const named = /filename="([^"]+)"/.exec(disposition)
      const filename = named?.[1] ?? `project-${projectId}-backup.zip`
      const url = URL.createObjectURL(await response.blob())
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch {
      exportError.value = 'Backup download failed. Check that the API is running.'
    } finally {
      isExporting.value = false
    }
  }

  /** Preview-first import: validate the package and show what would change. */
  async function previewImportPackage(file: File) {
    if (isImporting.value) return
    importError.value = ''
    importStatus.value = ''
    resetPreviewState()
    const version = previewVersion
    previewController = new AbortController()
    pendingPackage = file
    importFileName.value = file.name
    isLoadingPreview.value = true
    try {
      const response = await fetchApi('/projects/backups/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/zip' },
        body: file,
        signal: previewController.signal,
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Preview failed')
      }
      const report: BackupPreviewSummary = await response.json()
      if (version !== previewVersion) return
      preview.value = report
      overwriteConfirmed.value = false
    } catch (error) {
      if (version !== previewVersion) return
      resetPreviewState()
      importError.value =
        error instanceof Error
          ? `Backup preview failed. ${error.message}`
          : 'Backup preview failed. Check that the API is running.'
    } finally {
      if (version === previewVersion) isLoadingPreview.value = false
    }
  }

  function discardPreview() {
    if (isImporting.value) return
    importError.value = ''
    resetPreviewState()
  }

  /** Execute the import for the previously previewed package.

   *  A package whose project id already exists requires the explicit
   *  overwrite confirmation before this will send ``overwrite=true``. */
  async function importPreviewedPackage() {
    if (isImporting.value || isLoadingPreview.value) return
    importError.value = ''
    importStatus.value = ''
    const file = pendingPackage
    const summary = preview.value
    if (!file || !summary) {
      importError.value = 'Select a project package first.'
      return
    }
    if (summary.target_exists && !summary.can_overwrite) {
      importError.value = '旧版备份不完整，不能覆盖现有项目。'
      return
    }
    if (summary.target_exists && !overwriteConfirmed.value) {
      importError.value = '目标项目已存在：需要先确认覆盖，才能执行导入。'
      return
    }

    isImporting.value = true
    try {
      const query = summary.target_exists ? '?overwrite=true' : ''
      const response = await fetchApi(`/projects/backups/import${query}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/zip' },
        body: file,
      })
      if (!response.ok) {
        const detail = await readErrorDetail(response)
        throw new Error(detail.message || 'Import failed')
      }
      const result: BackupImportSummary = await response.json()
      importStatus.value = result.replaced_existing
        ? `项目包已导入，覆盖了现有项目「${result.project.title}」。`
        : `项目包已导入为新项目「${result.project.title}」。`
      resetPreviewState()

      // Refresh the project list and switch to the imported project so its
      // data fans out through the regular workspace load path.
      const projectsResponse = await fetchApi('/projects')
      if (projectsResponse.ok) {
        useProjectsStore().projects = await projectsResponse.json()
      }
      if (ws().activeProjectId === result.project.id) ws().reloadActiveProject()
      else ws().activeProjectId = result.project.id
    } catch (error) {
      importError.value =
        error instanceof Error
          ? `导入失败。${error.message}`
          : '导入失败。请检查 API 是否正在运行。'
    } finally {
      isImporting.value = false
    }
  }

  return {
    isExporting,
    exportError,
    importFileName,
    preview,
    isLoadingPreview,
    isImporting,
    importError,
    importStatus,
    overwriteConfirmed,
    exportActiveProjectBackup,
    previewImportPackage,
    importPreviewedPackage,
    discardPreview,
  }
})
