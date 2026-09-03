import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const read = (relative) =>
  readFileSync(new URL(relative, import.meta.url), 'utf8')

const workspaceStore = read('../src/stores/workspace.ts')
const formatUtils = read('../src/utils/format.ts')
const manuscriptStore = read('../src/stores/manuscript.ts')
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
  assert.match(formatUtils, /return value\.split\('_'\)\.join\(' '\)/)
})

test('proposal acceptance refreshes dependent collections in one batch', () => {
  assert.match(
    manuscriptStore,
    /await Promise\.all\(\[\s*loadManuscriptScenes\(projectId\),\s*loadManuscriptRevisions\(projectId\),\s*reviews\.loadWritebackProposals\(projectId\),?\s*\]\)/s,
  )
})

test('projects live in a dialog instead of occupying the sidebar', () => {
  assert.doesNotMatch(appSidebar, /class="project-list"/)
  assert.match(projectDialog, /<dialog/)
  assert.match(projectDialog, /Open project/)
  assert.doesNotMatch(snowflakeWorkspace, /class="create-project"/)
})

test('the entire Snowflake step card is the selector target', () => {
  const selectorStart = snowflakeWorkspace.indexOf('<button\n              class="step-selector"')
  const selectorEnd = snowflakeWorkspace.indexOf('</button>', selectorStart)
  const selectorMarkup = snowflakeWorkspace.slice(selectorStart, selectorEnd)
  assert.ok(selectorStart >= 0)
  assert.match(selectorMarkup, /step\.number/)
  assert.match(selectorMarkup, /step\.title/)
  assert.match(selectorMarkup, /step\.description/)
  assert.match(snowflakeWorkspace, /v-if="!isStepWorkspaceOpen" class="pipeline"/)
  assert.match(snowflakeWorkspace, /<template v-else>/)
  assert.match(snowflakeWorkspace, /All Snowflake steps/)
})

test('Snowflake generation exposes and sends a bounded upstream context budget', () => {
  assert.match(snowflakeWorkspace, /v-model\.number="previousArtifactsContextChars"/)
  assert.match(snowflakeWorkspace, /min="1000"/)
  assert.match(snowflakeWorkspace, /max="400000"/)
  assert.match(
    snowflakeStore,
    /previous_artifacts_context_chars: contextChars/,
  )
  assert.match(
    snowflakeStore,
    /contextChars < 1000 \|\| contextChars > 400000/,
  )
})
