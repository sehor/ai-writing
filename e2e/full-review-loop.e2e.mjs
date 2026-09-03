// P1-08 full review-loop E2E: real FastAPI backend (temp SQLite data root),
// real Vite dev server, real Playwright Chromium, local deterministic provider.
//
// Encodes the happy path from docs/older/ai-writing-improvement-plan.md section 九:
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

// Parsed by backend/app/snowflake_compiler/scene_parser.py into exactly two
// clean Scene Contract proposals (sequences 2/3 dodge the existing contract;
// 'Chapter 1' hints resolve to the chapter created in step 5; required canon
// resolves against the accepted Mira entity, so no parse warnings appear).
const SCENE_LIST_ARTIFACT = [
  '# Scene List',
  '',
  "### Scene 2: The Patron's Letter",
  '- POV: Mira',
  '- Goal: Decode the letter hidden inside the archive ledger.',
  '- Conflict: The letter names a patron Mira has promised to protect.',
  '- Turning point: The ledger page is newer than its binding.',
  '- Required Canon: Mira',
  "- Forbidden facts: The patron's identity.",
  '- Open threads: Who rewrote the map?',
  '- Chapter hint: Chapter 1',
  '',
  '### Scene 3: The Redrawn Door',
  '- POV: Mira',
  '- Goal: Use the redrawn map to open the sealed archive door.',
  '- Conflict: The door opens onto a room that should not exist.',
  '- Turning point: The room already holds her own archived notes.',
  '- Required Canon: Mira',
  "- Forbidden facts: The patron's identity.",
  '- Open threads: Who filed those notes?',
  '- Chapter hint: Chapter 1',
  '',
].join('\n')

const EDITED_SCENE_CONTENT = [
  'The archive door answered this time.',
  '',
  'Mira pressed the altered map flat against the stone and felt the city',
  'hold its breath before letting her in. EDITED-FOR-REVISION-E2E.',
].join('\n')

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

async function openProject(page, title) {
  await page.getByRole('button', { name: 'Open project' }).click()
  await page.locator('.project-picker-list button', { hasText: title }).click()
}

/** Wait for API truth without refreshing the UI: the app must poll on its own. */
async function waitForJobs(check, { timeoutMs = 60000, label } = {}) {
  const deadline = Date.now() + timeoutMs
  let lastError = null
  while (Date.now() < deadline) {
    try {
      const value = await check()
      if (value) return
    } catch (error) {
      lastError = error
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
  await page.getByRole('button', { name: 'Open project' }).click()
  await page.getByText('Create new project', { exact: true }).click()
  await page.getByPlaceholder('The Glass City').fill(PROJECT_TITLE)
  await page
    .getByPlaceholder(/disgraced cartographer discovers/)
    .fill(PROJECT_PREMISE)
  await page.getByRole('button', { name: 'Create Project' }).click()
  await page
    .locator('.topbar-notice', {
      hasText: `Project "${PROJECT_TITLE}" created successfully.`,
    })
    .waitFor({ state: 'visible' })
  await page.locator('.topbar h2', { hasText: PROJECT_TITLE }).waitFor({ state: 'visible' })
  assert.equal(await page.locator('.sidebar .project-list').count(), 0)
  await page.getByRole('button', { name: 'Open project' }).click()
  await page.locator('.project-picker-list button', { hasText: PROJECT_TITLE }).waitFor()
  await page.getByRole('button', { name: 'Close project dialog' }).click()

  const projects = await client.get('/projects')
  const project = projects.find((item) => item.title === PROJECT_TITLE)
  assert.ok(project, 'project was created through the UI and is visible over the API')

  // ------------------------------------------------------------------
  // 2. Snowflake workspace: save the Step 7 artifact (character bible).
  // ------------------------------------------------------------------
  step('save Step 7 character bible artifact')
  await page.getByText('Character Bible', { exact: true }).click()
  await page.getByRole('heading', { name: 'Step 7: Character Bible' }).waitFor()
  await page.getByRole('button', { name: 'All Snowflake steps' }).waitFor()
  assert.equal(await page.locator('.steps').count(), 0)
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
  const originalProposal = (await client.get('/projects/' + project.id + '/manuscript/proposals'))[0]
  const editedContent = originalProposal.content + '\n\nAUTHOR_REVIEWED_EDIT: Mira keeps her own notes.'
  await page.getByTestId('proposal-draft-content').fill(editedContent)
  // Reload restores the local draft without changing the stored AI original.
  await page.reload()
  await openProject(page, PROJECT_TITLE)
  await clickNavButton(page, 'Manuscript')
  assert.equal(await page.getByTestId('proposal-draft-content').inputValue(), editedContent)
  await page
    .locator('.proposal-workspace .proposal-detail')
    .getByRole('button', { name: 'Accept · 保存并分析', exact: true })
    .click()

  await page
    .getByText('Chapter 1: ' + CHAPTER_TITLE + ' / Version 1')
    .first()
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // 7. All four jobs run asynchronously; the UI reaches terminal state unaided.
  // ------------------------------------------------------------------
  step('wait for the automatic wiki index + consistency + write-back analysis jobs')
  const revision = (await client.get('/projects/' + project.id + '/manuscript/revisions'))[0]
  assert.equal(revision.content, editedContent)
  assert.equal((await client.get('/projects/' + project.id + '/manuscript/revisions')).length, 1)
  assert.equal((await client.get('/projects/' + project.id + '/manuscript/proposals'))
    .find((proposal) => proposal.id === originalProposal.id).content, originalProposal.content)
  const POST_ACCEPT_TYPES = ['llm_wiki_ingest', 'consistency_analysis', 'writeback_analysis', 'clp_extraction']
  await waitForJobs(
    async () => {
      const jobs = await client.get('/projects/' + project.id + '/outbox-jobs')
      const relevant = jobs.filter((job) => job.aggregate_id === revision.id)
      // Canon and manuscript acceptances each enqueue their own wiki index job,
      // so require every type present and EVERY relevant job succeeded.
      if (relevant.length !== POST_ACCEPT_TYPES.length) return false
      assert.deepEqual(relevant.map((job) => job.job_type).sort(), [...POST_ACCEPT_TYPES].sort())
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
  await page.locator('.post-accept-analysis article').filter({ hasText: 'CLP extraction' })
    .locator('.severity-chip', { hasText: 'succeeded' }).waitFor({ state: 'visible' })
  assert.equal(chipCount, 4, 'all four revision job types are rendered')
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

  // Deterministic REST fixtures exercise the same human-review UI as CLP output.
  step('review StoryThread and NarrativeRelation proposals through the browser')
  const thread = await client.post('/projects/' + project.id + '/story-threads', {
    thread_type: 'mystery', title: 'Who rewrote the map?', status: 'developing',
  })
  const sourceRef = 'manuscript_revision:' + revisions[0].id
  const evidence = [{ source_ref: sourceRef, excerpt: 'Mira keeps her own notes.' }]
  const narrativeCandidates = [
    {
      target: 'story_thread_status', action: 'update', title: 'Archive mystery becomes dormant',
      target_record_id: thread.id,
      payload: { subject_id: thread.id, from_state: 'developing', proposed_state: 'dormant',
        confidence: 0.8, source_ref: sourceRef, evidence },
    },
    {
      target: 'narrative_relation', action: 'create', title: 'Mira suspects the patron',
      payload: { source: 'character:Mira', target: 'character:Patron', relation: 'SUSPECTS',
        valid_from: 1, confidence: 0.9, source_ref: sourceRef, evidence },
    },
  ]
  for (const candidate of narrativeCandidates) {
    await client.post('/projects/' + project.id + '/writeback/proposals', {
      ...candidate, rationale: 'Reviewable E2E fixture', source_ref: sourceRef,
    })
  }
  await clickNavButton(page, 'Graph')
  await page.getByRole('button', { name: '刷新 Narrative', exact: true }).click()
  await page.locator(`[data-thread-id="${thread.id}"]`).waitFor({ state: 'visible' })
  await clickNavButton(page, 'Manuscript')
  await page.locator('.writeback-review button', { hasText: 'Refresh' }).first().click()
  for (const candidate of narrativeCandidates) {
    await page.locator('.writeback-review .proposal-list button', { hasText: candidate.title }).click()
    const detail = page.locator('.writeback-review .proposal-detail')
    await detail.locator('.clp-evidence blockquote', { hasText: 'Mira keeps her own notes.' }).waitFor({ state: 'visible' })
    await detail.getByRole('button', { name: 'Accept', exact: true }).click()
    await page.locator('.writeback-review .save-state', { hasText: 'Write-back accepted and applied.' }).waitFor({ state: 'visible' })
  }
  await clickNavButton(page, 'Graph')
  await page.locator(`[data-thread-id="${thread.id}"] .step-chip`, { hasText: 'dormant' }).waitFor({ state: 'visible' })
  await page.locator('.narrative-panel td', { hasText: 'SUSPECTS' }).waitFor({ state: 'visible' })
  await page.locator('.director-report').waitFor({ state: 'visible' })
  assert.equal((await client.get('/projects/' + project.id + '/story-threads'))[0].status, 'dormant')
  assert.equal((await client.get('/projects/' + project.id + '/narrative/relations')).length, 1)
  await clickNavButton(page, 'Manuscript')
  if (process.env.AI_WRITING_E2E_SCREENSHOT) {
    await page.locator('.manuscript-setup > summary').click()
    await page.screenshot({ path: process.env.AI_WRITING_E2E_SCREENSHOT, fullPage: true })
    await page.locator('.manuscript-setup > summary').click()
  }

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
  await openProject(page, PROJECT_TITLE)
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

  // ------------------------------------------------------------------
  // 11. Step 8 structured compiler: save the scene list, parse it into
  //     Scene Contract proposals, then batch-accept every pending one.
  //     Sequences 2/3 avoid the existing contract at sequence 1; the
  //     'Chapter 1' hints resolve to the chapter created in step 5 and
  //     'Mira' resolves against the accepted Canon entity.
  // ------------------------------------------------------------------
  step('save Step 8 scene list artifact')
  // Step 10 left the workspace on the Manuscript section; the Snowflake
  // step rail only exists while that section is mounted.
  await clickNavButton(page, 'Snowflake')
  await page.getByRole('button', { name: 'Open step 8: Scene List' }).click()
  await page.locator('.artifact-editor textarea').fill(SCENE_LIST_ARTIFACT)
  await page.getByRole('button', { name: 'Save Artifact' }).click()
  await page
    .locator('.artifact-editor .save-state', { hasText: 'Artifact saved.' })
    .waitFor({ state: 'visible' })

  step('parse Step 8 into Scene Proposals')
  await page
    .getByRole('heading', { name: 'Step 8: Parse into Scene Proposals' })
    .waitFor({ state: 'visible' })
  await page.getByRole('button', { name: 'Parse Scene Proposals' }).click()
  await page
    .locator('.compile-panel .save-state', { hasText: 'Parsed 2 scene proposal(s).' })
    .waitFor({ state: 'visible' })
  const proposalRows = page.locator('.scene-proposal-table tbody tr')
  await proposalRows.first().waitFor({ state: 'visible' })
  assert.equal(await proposalRows.count(), 2, 'both parsed scene proposals are listed')
  await page
    .locator('.scene-proposal-table tbody tr', { hasText: "The Patron's Letter" })
    .locator('input[type="checkbox"]')
    .waitFor({ state: 'visible' })

  step('batch-accept all pending scene proposals')
  await page.getByRole('button', { name: 'Accept All Pending' }).click()
  await page
    .locator('.compile-panel .save-state', {
      hasText: 'Created 2 scene contract(s) from parsed proposals.',
    })
    .waitFor({ state: 'visible' })

  const contractsAfterBatch = await client.get('/projects/' + project.id + '/scene-contracts')
  const patronContract = contractsAfterBatch.find((item) => item.title === "The Patron's Letter")
  const doorContract = contractsAfterBatch.find((item) => item.title === 'The Redrawn Door')
  assert.ok(patronContract, 'batch acceptance created the first parsed contract')
  assert.ok(doorContract, 'batch acceptance created the second parsed contract')
  assert.equal(patronContract.sequence, 2)
  assert.equal(doorContract.sequence, 3)
  assert.ok(patronContract.chapter_id, 'chapter hint resolved to the existing chapter')
  assert.equal(patronContract.chapter_id, doorContract.chapter_id, 'same chapter for both hints')
  assert.match(patronContract.pov, /Mira/)
  assert.ok(
    patronContract.required_canon,
    'required canon names resolved against the Canon DB',
  )

  const batchProposals = await client.get('/projects/' + project.id + '/snowflake/scene-proposals')
  assert.equal(batchProposals.length, 2)
  assert.ok(
    batchProposals.every((item) => item.status === 'accepted'),
    'every parsed proposal moved to accepted',
  )

  step('new contracts are visible in the Manuscript workspace')
  await clickNavButton(page, 'Manuscript')
  await page
    .locator('.scene-list button', { hasText: "2. The Patron's Letter" })
    .waitFor({ state: 'visible' })
  await page
    .locator('.scene-list button', { hasText: '3. The Redrawn Door' })
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // 12. Direct edit of an accepted manuscript scene creates Version 2.
  // ------------------------------------------------------------------
  step('edit the accepted scene draft into Version 2')
  const scenesBeforeEdit = await client.get('/projects/' + project.id + '/manuscript/scenes')
  const editedScene = scenesBeforeEdit.find((item) => item.title.includes(SCENE_TITLE))
  assert.ok(editedScene, 'accepted scene from step 6 is present')
  const originalContent = editedScene.content

  const archiveItem = page
    .locator('.accepted-manuscript .accepted-item')
    .filter({ hasText: SCENE_TITLE })
  await archiveItem.getByRole('button', { name: 'Edit' }).click()
  await page.locator('.manuscript-edit textarea').fill(EDITED_SCENE_CONTENT)
  await page.getByRole('button', { name: 'Save Version' }).click()
  await page
    .locator('.accepted-manuscript .accepted-item p.eyebrow', { hasText: 'Version 2' })
    .waitFor({ state: 'visible' })

  const scenesAfterEdit = await client.get('/projects/' + project.id + '/manuscript/scenes')
  assert.equal(scenesAfterEdit[0].version, 2, 'direct edit bumps the scene to version 2')
  assert.equal(scenesAfterEdit[0].content, EDITED_SCENE_CONTENT, 'edited content is current')
  const revisionsAfterEdit = await client.get(
    '/projects/' + project.id + '/manuscript/revisions',
  )
  assert.equal(revisionsAfterEdit.length, 2, 'the edit filed exactly one new revision')
  assert.deepEqual(
    revisionsAfterEdit.map((revision) => revision.version).sort(),
    [1, 2],
    'revisions v1 and v2 exist after the edit',
  )
  await page
    .locator('.revision-history .revision-item p.eyebrow', { hasText: 'Version 2' })
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // 13. Restore revision 1: becomes the newest version with the
  //     original content back; history keeps all three revisions.
  // ------------------------------------------------------------------
  step('restore revision 1 as a new current version')
  const versionOneItem = page.locator('.revision-history .revision-item').filter({
    has: page.locator('p.eyebrow', { hasText: /^Version 1$/ }),
  })
  await versionOneItem.getByRole('button', { name: 'Restore' }).click()
  await page
    .locator('.accepted-manuscript .accepted-item p.eyebrow', { hasText: 'Version 3' })
    .waitFor({ state: 'visible' })

  const scenesAfterRestore = await client.get('/projects/' + project.id + '/manuscript/scenes')
  assert.equal(scenesAfterRestore[0].version, 3, 'restore files a brand-new version')
  assert.equal(
    scenesAfterRestore[0].content,
    originalContent,
    'restored scene carries the original revision content again',
  )
  const revisionsAfterRestore = await client.get(
    '/projects/' + project.id + '/manuscript/revisions',
  )
  assert.equal(revisionsAfterRestore.length, 3, 'all three revisions are preserved')
  assert.deepEqual(
    revisionsAfterRestore.map((revision) => revision.version).sort(),
    [1, 2, 3],
    'revision history holds versions 1..3',
  )
  const restoredRevision = revisionsAfterRestore.find((revision) => revision.version === 3)
  assert.equal(restoredRevision.content, originalContent, 'v3 revision stores the restored prose')
  await page
    .locator('.revision-history .revision-item p.eyebrow', { hasText: 'Version 3' })
    .waitFor({ state: 'visible' })

  // A stale browser edit must survive a competing writer and an explicit review.
  step('reject a stale manual save and preserve the draft through conflict review')
  await archiveItem.getByRole('button', { name: 'Edit', exact: true }).click()
  const staleDraft = 'MY_UNSAVED_CONFLICT_DRAFT'
  await page.locator('.manuscript-edit textarea').fill(staleDraft)
  await client.put('/projects/' + project.id + '/manuscript/scenes/' + editedScene.scene_id, {
    title: editedScene.title,
    content: 'OTHER_WINDOW_SAVED_TEXT',
    expected_scene_version: 3,
  })
  const rejected = page.waitForResponse(response =>
    response.request().method() === 'PUT' && response.url().endsWith('/manuscript/scenes/' + editedScene.scene_id),
  )
  await page.getByRole('button', { name: 'Save Version', exact: true }).click()
  assert.equal((await rejected).status(), 409)
  const conflict = page.getByRole('region', { name: '正文版本冲突' })
  await conflict.getByText('OTHER_WINDOW_SAVED_TEXT', { exact: true }).waitFor()
  assert.equal(await page.locator('.manuscript-edit textarea').inputValue(), staleDraft)
  assert.equal(await page.getByRole('button', { name: 'Save Version', exact: true }).isDisabled(), true)
  const afterConflict = await client.get('/projects/' + project.id + '/manuscript/revisions')
  assert.equal(afterConflict.length, 4, 'rejected save did not file a revision')
  assert.equal(afterConflict.find(revision => revision.version === 4).content, 'OTHER_WINDOW_SAVED_TEXT')
  await conflict.getByRole('button', { name: '已核对当前正文，保留我的编辑' }).click()
  assert.equal(await page.locator('.manuscript-edit textarea').inputValue(), staleDraft)
  assert.equal((await client.get('/projects/' + project.id + '/manuscript/revisions')).length, 4,
    'acknowledging the current version must not save automatically')
  await page.getByRole('button', { name: 'Save Version', exact: true }).click()
  await page.locator('.accepted-manuscript .accepted-item p.eyebrow', { hasText: 'Version 5' }).waitFor()
  const afterRebase = await client.get('/projects/' + project.id + '/manuscript/scenes')
  assert.equal(afterRebase[0].version, 5)
  assert.equal(afterRebase[0].content, staleDraft)
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
  page.on('dialog', (dialog) => dialog.accept())

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
