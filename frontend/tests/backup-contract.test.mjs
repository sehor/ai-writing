import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const backupsStore = readFileSync(new URL('../src/stores/backups.ts', import.meta.url), 'utf8')
const sidebar = readFileSync(new URL('../src/components/BackupWorkspace.vue', import.meta.url), 'utf8')
const types = readFileSync(new URL('../src/types/project.ts', import.meta.url), 'utf8')

test('backup entry downloads the active project ZIP package', () => {
  assert.match(backupsStore, /exportActiveProjectBackup/)
  assert.match(backupsStore, /\/projects\/\$\{projectId\}\/backup/)
  // Download goes through a blob object URL, not a navigation away from the app.
  assert.match(backupsStore, /createObjectURL/)
  assert.match(backupsStore, /anchor\.download/)
  assert.match(sidebar, /导出项目包/)
})

test('import is preview-first: preview runs before any import call', () => {
  assert.match(types, /export type BackupPreviewSummary/)
  assert.match(types, /target_exists: boolean/)
  assert.match(backupsStore, /\/projects\/backups\/preview/)
  assert.match(backupsStore, /\/projects\/backups\/import/)
  // The import action refuses to run without a completed preview.
  assert.match(backupsStore, /if \(!file \|\| !summary\)/)
  // Preview state resets before a new file is parsed.
  assert.match(backupsStore, /previewImportPackage\(file: File\)/)
})

test('overwrite requires an explicit confirmation when the target exists', () => {
  assert.match(backupsStore, /summary\.target_exists && !overwriteConfirmed\.value/)
  // Only a confirmed conflict sends overwrite=true to the API.
  assert.match(
    backupsStore,
    /summary\.target_exists \? '\?overwrite=true' : ''/,
  )
  assert.match(sidebar, /目标项目已存在：导入将覆盖现有项目，请先确认覆盖。/)
  assert.match(sidebar, /确认覆盖现有项目/)
  assert.match(sidebar, /覆盖并导入/)
  // The confirm button stays disabled until the checkbox flips.
  assert.match(
    sidebar.replace(/\s+/g, ''),
    /:disabled="isImporting\|\|\(backupPreview\.target_exists&&\(!backupPreview\.can_overwrite\|\|!overwriteConfirmed\)\)"/,
  )
})

test('a finished import refreshes the project list and selects the restored project', () => {
  assert.match(backupsStore, /useProjectsStore\(\)\.projects = await projectsResponse\.json\(\)/)
  assert.match(backupsStore, /context\.activeProjectId = result\.project\.id/)
  assert.match(sidebar, /data-testid="confirm-import"/)
})
test('backup preview preserves its safeguards inside the project dialog', () => {
  assert.match(sidebar, /class="backup-panel" aria-label="Backup and restore"/)
  assert.match(sidebar, /useBackupsStore/)
})
