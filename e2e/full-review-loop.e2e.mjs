// P1-08 full review-loop E2E: real FastAPI backend (temp SQLite data root),
// real Vite dev server, real Playwright Chromium, local deterministic provider.
//
// Encodes the happy path from docs/ai-writing-improvement-plan.md section 九:
//   create project -> save Step 7 -> extract Canon proposals -> accept Canon ->
//   create Chapter + Scene contract -> create manuscript proposal -> accept it
//   -> automatic post-acceptance analyses succeed -> accept a Canon write-back
//   -> Canon updated -> Export Markdown -> backend restart -> everything persists.
//
// Every /api call the page makes goes through the Vite proxy to the REAL
// backend. Nothing is mocked.

import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import {
  PORTS,
  api,
  launchBrowser,
  mkTempRoot,
  pollUntil,
  reportFailure,
  rmTempRoot,
  sleep,
  startBackend,
  startVite,
  stopBackend,
  stopVite,
} from './lib/harness.mjs'

const BACKEND_PORT = PORTS.fullReviewBackend // 8131
const VITE_PORT = PORTS.fullReviewVite // 5175

const PROJECT_TITLE = 'Mira Archive'
const PROJECT_PREMISE = 'A cartographer maps a city that resists memory.'
const CHAPTER_TITLE = 'The Locked Map'
const SCENE_TITLE = 'Archive Threshold'

// Parsed by backend/app/snowflake_compiler/canon_extractor.py into exactly one
// Canon CREATE proposal ("Create canon character: Mira").
const CHARACTER_BIBLE = [
  '# Character Bible',
  '',
  '### Character: Mira',
  '- Type: character',
  '- Summary: Archivist of the Glass City who maps sealed doors.',
  '- Current state: Testing the archive door with the altered map.',
  "- Constraints: Never reveals the patron's identity.",
  '- Last seen: chapter_1',
  '- Timeline notes: Found the self-redrawing map in scene 1.',
  '',
].join('\n')

const CANON_STATE_AFTER_WRITEBACK =
  'Inside the sealed archive; the redrawn map answers to her hand.'

const UPDATE_WRITEBACK_RATIONALE =
  'Seeded via POST /api/projects/{id}/writeback/proposals by this E2E. ' +
  'Documented deviation: the deterministic provider auto-generates a memory-record ' +
  '"Prose sample" proposal after acceptance, but no action=update proposal targeting ' +
  'the Canon record, so an update proposal is seeded over REST and then ACCEPTED ' +
  'THROUGH THE BROWSER UI to keep the human-review contract intact.'

let tempRoot = null
let backend = null
let vite = null
let browser = null

function step(message) {
  console.log('[full-review-loop] ' + message)
}

async function clickNavButton(page, name) {
  await page.locator('.sidebar nav.nav button', { hasText: name }).first().click()
}

/** Click Refresh inside a panel until check(panel) holds (deterministic UI wait). */
async function refreshPanelUntil(page, panelSelector, check, { timeoutMs = 60000, label } = {}) {
  const deadline = Date.now() + timeoutMs
  let lastError = null
  while (Date.now() < deadline) {
    try {
      const value = await check()
      if (value) return
    } catch (error) {
      lastError = error
    }
    const refresh = page.locator(panelSelector + ' button', { hasText: 'Refresh' }).first()
    if (await refresh.isVisible().catch(() => false)) {
      await refresh.click()
    }
    await sleep(700)
  }
  throw new Error(
    'Timed out waiting for ' + label + (lastError ? '; last error: ' + lastError.message : ''),
  )
}

async function run(page) {
  const client = api(BACKEND_PORT)

  // ------------------------------------------------------------------
  // 1. Create the project through the UI (Snowflake workspace form).
  // ------------------------------------------------------------------
  step('open app and create project ' + PROJECT_TITLE)
  await page.goto(vite.url + '/')
  await page.locator('.create-project').waitFor({ state: 'visible' })
  await page.getByPlaceholder('The Glass City').fill(PROJECT_TITLE)
  await page
    .getByPlaceholder(/disgraced cartographer discovers/)
    .fill(PROJECT_PREMISE)
  await page.getByRole('button', { name: 'Create Project' }).click()
  await page.locator('.topbar h2', { hasText: PROJECT_TITLE }).waitFor({ state: 'visible' })
  await page
    .locator('.sidebar .project-list button', { hasText: PROJECT_TITLE })
    .waitFor({ state: 'visible' })

  const projects = await client.get('/projects')
  const project = projects.find((item) => item.title === PROJECT_TITLE)
  assert.ok(project, 'project was created through the UI and is visible over the API')

  // ------------------------------------------------------------------
  // 2. Snowflake workspace: save the Step 7 artifact (character bible).
  // ------------------------------------------------------------------
  step('save Step 7 character bible artifact')
  await page
    .getByRole('button', { name: 'Open step 7: Character Bible' })
    .click()
  await page.locator('.artifact-editor textarea').fill(CHARACTER_BIBLE)
  await page.getByRole('button', { name: 'Save Artifact' }).click()
  await page
    .locator('.artifact-editor .save-state', { hasText: 'Artifact saved.' })
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // 3. Snowflake compiler panel: extract Canon proposals from Step 7.
  // ------------------------------------------------------------------
  step('compile Step 7 into Canon proposals')
  await page
    .getByRole('heading', { name: 'Step 7: Compile into Canon Proposals' })
    .waitFor({ state: 'visible' })
  await page.getByRole('button', { name: 'Extract Canon Proposals' }).click()
  await page
    .locator('.compile-summary')
    .filter({ hasText: '1 proposal(s): 1 create, 0 update.' })
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // 4. Accept the Canon proposal in Manuscript > Write-backs (the real
  //    review surface the compiler points at).
  // ------------------------------------------------------------------
  step('accept the Canon create proposal via the Write-backs panel')
  await clickNavButton(page, 'Manuscript')
  const miraProposalItem = page
    .locator('.writeback-review .proposal-list button')
    .filter({ hasText: 'Create canon character: Mira' })
  await miraProposalItem.waitFor({ state: 'visible' })
  await miraProposalItem.click()
  await page
    .locator('.writeback-review .proposal-detail')
    .getByRole('button', { name: 'Accept', exact: true })
    .click()
  await page
    .locator('.writeback-review .save-state', { hasText: 'Write-back accepted and applied.' })
    .waitFor({ state: 'visible' })

  const canonEntities = await client.get('/projects/' + project.id + '/canon/entities')
  const mira = canonEntities.find((entity) => entity.name === 'Mira')
  assert.ok(mira, 'Canon entity Mira exists after accepting the proposal')
  assert.equal(mira.version, 1, 'Canon entity Mira starts at version 1')

  // Canon workspace shows the accepted entity.
  step('verify Mira is visible in the Canon workspace')
  await clickNavButton(page, 'Canon')
  await page
    .locator('.canon-list button', { hasText: 'Mira' })
    .waitFor({ state: 'visible' })
  await page.locator('.canon-list button', { hasText: 'Mira' }).click()
  // Product behavior (identical at git HEAD): selecting a list entry re-baselines
  // the editor draft but does not copy entity fields into it (restoreEntryDraft
  // applies cached drafts only), so the editor intentionally stays empty. The
  // active list row is the Canon-workspace visibility proof; field values are
  // asserted over the API.
  await page.locator('.canon-list button.active', { hasText: 'Mira' })
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // 5. Manuscript workspace: create Chapter and Scene contract.
  // ------------------------------------------------------------------
  step('create Chapter and Scene contract')
  await clickNavButton(page, 'Manuscript')
  await page.getByRole('button', { name: 'New Chapter' }).click()
  await page
    .locator('.chapter-editor input[type="number"]')
    .fill('1')
  await page
    .locator('.chapter-editor label', { hasText: 'Title' })
    .locator('input')
    .fill(CHAPTER_TITLE)
  await page
    .locator('.chapter-editor label', { hasText: 'Summary' })
    .locator('textarea')
    .fill('Mira reaches the sealed archive.')
  await page.getByRole('button', { name: 'Create Chapter' }).click()
  await page
    .locator('.chapter-list button', { hasText: 'Chapter 1: ' + CHAPTER_TITLE })
    .waitFor({ state: 'visible' })

  await page.getByRole('button', { name: 'New Scene' }).click()
  await page
    .locator('.scene-editor select')
    .selectOption({ label: 'Chapter 1: ' + CHAPTER_TITLE })
  await page.locator('.scene-editor input[type="number"]').nth(0).fill('1')
  await page.getByPlaceholder('The map changes').fill(SCENE_TITLE)
  await page.getByPlaceholder('Lin Ye').fill('Mira')
  const sceneTextareas = page.locator('.scene-editor textarea')
  await sceneTextareas.nth(0).fill('Enter the sealed archive.') // Goal
  await sceneTextareas.nth(1).fill('The map refuses the door.') // Conflict
  await sceneTextareas.nth(2).fill('The map redraws itself.') // Turning Point
  await sceneTextareas.nth(3).fill('Mira carries the altered map.') // Required Canon
  await sceneTextareas.nth(4).fill("The patron's identity.") // Forbidden Facts
  await sceneTextareas.nth(5).fill('Who changed the map?') // Open Threads
  await page.getByRole('button', { name: 'Create Scene', exact: true }).click()
  await page
    .locator('.scene-list button', { hasText: '1. ' + SCENE_TITLE })
    .waitFor({ state: 'visible' })

  const scenes = await client.get('/projects/' + project.id + '/scene-contracts')
  const scene = scenes.find((item) => item.title === SCENE_TITLE)
  assert.ok(scene, 'scene contract persisted with goal/conflict/turning point fields')
  assert.equal(scene.pov, 'Mira')
  assert.match(scene.goal, /sealed archive/)
  assert.match(scene.conflict, /refuses the door/)
  assert.match(scene.turning_point, /redraws itself/)
  assert.ok(scene.chapter_id, 'scene contract assigned to the new chapter')

  // ------------------------------------------------------------------
  // 6. Create Proposal -> Accept -> Version 1 indicator.
  // ------------------------------------------------------------------
  step('create and accept the manuscript proposal')
  await page.getByRole('button', { name: 'Create Proposal', exact: true }).click()
  await page
    .locator('.proposal-workspace .proposal-detail h4', { hasText: '1. ' + SCENE_TITLE })
    .waitFor({ state: 'visible' })
  await page
    .locator('.proposal-workspace .proposal-detail')
    .getByRole('button', { name: 'Accept', exact: true })
    .click()

  await page
    .getByText('Chapter 1: ' + CHAPTER_TITLE + ' / Version 1')
    .first()
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // 7. Post-Acceptance Analysis: all three automatic jobs must succeed.
  //    (Dispatched inline right after the acceptance commit.)
  // ------------------------------------------------------------------
  step('wait for the automatic wiki index + consistency + write-back analysis jobs')
  const POST_ACCEPT_TYPES = ['llm_wiki_ingest', 'consistency_analysis', 'writeback_analysis']
  await refreshPanelUntil(
    page,
    '.post-accept-analysis',
    async () => {
      const jobs = await client.get('/projects/' + project.id + '/outbox-jobs')
      const relevant = jobs.filter((job) => POST_ACCEPT_TYPES.includes(job.job_type))
      // Canon and manuscript acceptances each enqueue their own wiki index job,
      // so require every type present and EVERY relevant job succeeded.
      if (relevant.length < POST_ACCEPT_TYPES.length) return false
      return relevant.every((job) => job.status === 'succeeded')
    },
    { label: 'all post-acceptance jobs succeeding', timeoutMs: 90000 },
  )
  const jobChips = page.locator('.post-accept-analysis article .severity-chip')
  await page
    .locator('.post-accept-analysis article')
    .filter({ hasText: 'Wiki index' })
    .first()
    .locator('.severity-chip', { hasText: 'succeeded' })
    .waitFor({ state: 'visible' })
  await page
    .locator('.post-accept-analysis article')
    .filter({ hasText: 'Consistency report' })
    .first()
    .locator('.severity-chip', { hasText: 'succeeded' })
    .waitFor({ state: 'visible' })
  await page
    .locator('.post-accept-analysis article')
    .filter({ hasText: 'Write-back suggestions' })
    .first()
    .locator('.severity-chip', { hasText: 'succeeded' })
    .waitFor({ state: 'visible' })
  const chipCount = await jobChips.count()
  assert.ok(chipCount >= 3, 'at least the three post-acceptance job chips are rendered')
  const succeededCount = await page
    .locator('.post-accept-analysis article .severity-chip', { hasText: 'succeeded' })
    .count()
  assert.equal(
    succeededCount,
    chipCount,
    'every rendered post-acceptance job chip reads succeeded',
  )

  // Revision History shows the accepted revision; consistency findings load.
  await page
    .locator('.revision-history .revision-item p.eyebrow', { hasText: 'Version 1' })
    .first()
    .waitFor({ state: 'visible' })
  await page
    .locator('.consistency-report')
    .waitFor({ state: 'visible' })
  assert.equal(
    await page.locator('.consistency-report .error-text').count(),
    0,
    'consistency findings area loads without an error banner',
  )

  const revisions = await client.get('/projects/' + project.id + '/manuscript/revisions')
  assert.equal(revisions.length, 1, 'exactly one accepted revision so far')
  assert.equal(revisions[0].version, 1)

  // ------------------------------------------------------------------
  // 8. References/Copilot write-backs: the deterministic provider
  //    auto-created a memory-record proposal. It generates no
  //    action=update Canon proposal, so seed one over REST (documented
  //    deviation) and ACCEPT IT IN THE BROWSER.
  // ------------------------------------------------------------------
  step('seed + browser-accept a Canon update write-back proposal')
  await page
    .locator('.writeback-review .proposal-list button')
    .filter({ hasText: 'Prose sample from 1. ' + SCENE_TITLE })
    .waitFor({ state: 'visible' })

  const seeded = await client.post('/projects/' + project.id + '/writeback/proposals', {
    target: 'canon_entity',
    action: 'update',
    title: 'Update canon character: Mira',
    rationale: UPDATE_WRITEBACK_RATIONALE,
    source_ref: 'manuscript_revision:' + revisions[0].id,
    target_record_id: mira.id,
    expected_version: mira.version,
    changes: {
      current_state: {
        before: mira.current_state,
        after: CANON_STATE_AFTER_WRITEBACK,
      },
    },
  })
  assert.equal(seeded.status, 'pending_review', 'seeded update proposal is pending review')

  await page.locator('.writeback-review button', { hasText: 'Refresh' }).first().click()
  const seededItem = page
    .locator('.writeback-review .proposal-list button')
    .filter({ hasText: 'Update canon character: Mira' })
  await seededItem.waitFor({ state: 'visible' })
  await seededItem.click()
  await page
    .locator('.writeback-review .proposal-detail')
    .getByRole('button', { name: 'Accept', exact: true })
    .click()
  await page
    .locator('.writeback-review .save-state', { hasText: 'Write-back accepted and applied.' })
    .waitFor({ state: 'visible' })

  const canonAfterUpdate = await client.get('/projects/' + project.id + '/canon/entities')
  const miraUpdated = canonAfterUpdate.find((entity) => entity.id === mira.id)
  assert.equal(miraUpdated.version, 2, 'accepted update bumps the Canon entity version')
  assert.equal(
    miraUpdated.current_state,
    CANON_STATE_AFTER_WRITEBACK,
    'accepted update applies the proposed current_state',
  )

  // ------------------------------------------------------------------
  // 9. Export Markdown shows the chapter heading.
  // ------------------------------------------------------------------
  step('export markdown')
  await page.getByRole('button', { name: 'Export Markdown' }).click()
  const exportedPre = page.locator('.export-output pre')
  await exportedPre.waitFor({ state: 'visible' })
  const exported = await exportedPre.textContent()
  assert.match(exported, new RegExp('^# ' + PROJECT_TITLE))
  assert.match(exported, /## Chapter 1: The Locked Map/)
  assert.match(exported, /### 1\. Archive Threshold/)

  // Wiki index files prove the LLM Wiki store also lives under the temp root.
  assert.ok(
    existsSync(join(tempRoot, 'projects', project.id, 'modules', 'llm_wiki', 'sources')),
    'LLM Wiki ingestion wrote under <AI_WRITING_DATA_ROOT>/projects/<project>',
  )

  // ------------------------------------------------------------------
  // 10. Restart the backend on the SAME temp root; reload; re-select;
  //     verify project/canon/manuscript persistence.
  // ------------------------------------------------------------------
  step('restart backend on the same temp root and verify persistence')
  await stopBackend(backend)
  backend = await startBackend({ dataRoot: tempRoot, port: BACKEND_PORT })
  await page.reload()
  await page
    .locator('.sidebar .project-list button', { hasText: PROJECT_TITLE })
    .waitFor({ state: 'visible' })
  await page.locator('.sidebar .project-list button', { hasText: PROJECT_TITLE }).click()
  await page.locator('.topbar h2', { hasText: PROJECT_TITLE }).waitFor({ state: 'visible' })

  // Canon persisted.
  await clickNavButton(page, 'Canon')
  await page.locator('.canon-list button', { hasText: 'Mira' }).waitFor({ state: 'visible' })
  await page.locator('.canon-list button', { hasText: 'Mira' }).click()
  await page.locator('.canon-list button.active', { hasText: 'Mira' })
    .waitFor({ state: 'visible' })

  // Manuscript persisted: chapter, scene contract, Version 1 scene + revision.
  await clickNavButton(page, 'Manuscript')
  await page
    .locator('.chapter-list button', { hasText: 'Chapter 1: ' + CHAPTER_TITLE })
    .waitFor({ state: 'visible' })
  await page
    .locator('.scene-list button', { hasText: '1. ' + SCENE_TITLE })
    .waitFor({ state: 'visible' })
  await page
    .getByText('Chapter 1: ' + CHAPTER_TITLE + ' / Version 1')
    .first()
    .waitFor({ state: 'visible' })
  await page
    .locator('.revision-history .revision-item p.eyebrow', { hasText: 'Version 1' })
    .first()
    .waitFor({ state: 'visible' })

  const revisionsAfterRestart = await client.get(
    '/projects/' + project.id + '/manuscript/revisions',
  )
  assert.equal(revisionsAfterRestart.length, 1, 'still exactly one revision after restart')
  assert.equal(revisionsAfterRestart[0].version, 1)
  const scenesAfterRestart = await client.get(
    '/projects/' + project.id + '/manuscript/scenes',
  )
  assert.equal(scenesAfterRestart.length, 1)
  assert.equal(scenesAfterRestart[0].version, 1)
}

async function main() {
  tempRoot = await mkTempRoot('ai-writing-e2e-full-')
  console.log('[full-review-loop] temp data root: ' + tempRoot)
  backend = await startBackend({ dataRoot: tempRoot, port: BACKEND_PORT })
  vite = await startVite({ port: VITE_PORT, backendPort: BACKEND_PORT })
  browser = await launchBrowser()

  const pageErrors = []
  const page = await browser.newPage()
  page.setDefaultTimeout(30000)
  page.on('pageerror', (error) => pageErrors.push(String(error)))

  try {
    await run(page)
    if (pageErrors.length > 0) {
      throw new Error('Uncaught page errors during the E2E:\n' + pageErrors.join('\n'))
    }
    console.log('[full-review-loop] PASS')
  } catch (error) {
    reportFailure(error, [backend])
    process.exitCode = 1
  } finally {
    await page.close().catch(() => {})
  }
}

try {
  await main()
} finally {
  if (browser) await browser.close().catch(() => {})
  if (vite) await stopVite(vite)
  if (backend) await stopBackend(backend)
  if (process.exitCode !== 1 && tempRoot) await rmTempRoot(tempRoot)
}
