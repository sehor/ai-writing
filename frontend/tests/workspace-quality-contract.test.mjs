import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const workspaceStore = read('../src/stores/workspace.ts')
const formatUtils = read('../src/utils/format.ts')
const appSidebar = read('../src/components/AppSidebar.vue')
const projectDialog = read('../src/components/ProjectDialog.vue')
const snowflakeWorkspace = read('../src/components/SnowflakeWorkspace.vue')
const snowflakeStore = read('../src/stores/snowflake.ts')

test('workspace global status keeps narrow safe patterns', () => {
  assert.match(workspaceStore, /type ApiStatus = 'checking' \| 'ok' \| 'offline'/)
  assert.match(workspaceStore, /const apiStatus = ref<ApiStatus>\('checking'\)/)
})

test('initial loading cannot overwrite a project selected or created in flight', () => {
  assert.match(workspaceStore, /\.\.\.loadedProjects, \.\.\.projectsStore\.projects/)
  assert.match(workspaceStore, /if \(!activeProjectId\.value\)/)
})

test('shared label formatting humanizes enum values without unsafe parsing', () => {
  assert.match(formatUtils, /value\.split\('_'\)\.join\(' '\)/)
})

// Commit refresh behavior is covered in manuscript-composition.test.ts.

test('projects live in a dialog instead of occupying the sidebar', () => {
  assert.doesNotMatch(appSidebar, /class="project-list"/)
  assert.match(projectDialog, /<dialog/)
  assert.match(projectDialog, /打开项目/)
  assert.doesNotMatch(snowflakeWorkspace, /class="create-project"/)
})

// Snowflake navigation, forms, and compiler controls have executable component tests.
test('Snowflake generation sends a bounded upstream context budget', () => {
  assert.match(
    snowflakeStore,
    /previous_artifacts_context_chars: contextChars/,
  )
  assert.match(
    snowflakeStore,
    /contextChars < 1000 \|\| contextChars > 400000/,
  )
})

test('Snowflake record actions use the record authority routes', () => {
  assert.match(snowflakeStore, /snowflake\/records\/\$\{step\}\/\$\{action\}/)
})
