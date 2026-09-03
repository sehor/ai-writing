// P1-08 failure-path E2E: LLM Wiki writes fail while core manuscript data
// must survive, the failure surfaces in the Manuscript workspace, and Retry
// from the UI repairs it without duplicating manuscript versions.
//
// How the failure is forced: BEFORE the backend boots, a regular FILE named
// exactly 'projects' is created inside the temp AI_WRITING_DATA_ROOT. Both
// file-backed stores root at <root>/projects, so every write below it fails:
//   - llm_wiki_ingest      (LocalFileLlmWiki ingest)
//   - writeback_analysis   (LocalMemplaceModule.persist_sample prose samples)
// while consistency_analysis stays DB-only and therefore succeeds.
//
// The Manuscript workspace Post-Acceptance Analysis panel surfaces all three
// job types (llm_wiki_ingest / consistency_analysis / writeback_analysis); the
// failed writeback_analysis AND llm_wiki_ingest jobs both get their UI Retry
// clicked here, and recovery of the wiki write path is proven by the ingested
// wiki sources plus the memplace prose-sample files landing under <root>/projects.

import assert from 'node:assert/strict'
import { existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { unlink } from 'node:fs/promises'
import {
  PORTS,
  api,
  blockWikiRootWithFile,
  launchBrowser,
  mkTempRoot,
  reportFailure,
  rmTempRoot,
  sleep,
  startBackend,
  startVite,
  stopBackend,
  stopVite,
} from './lib/harness.mjs'

const BACKEND_PORT = PORTS.wikiFailureBackend // 8132
const VITE_PORT = PORTS.wikiFailureVite // 5176

const PROJECT_TITLE = 'Fault Line Archive'
const PROJECT_PREMISE = 'A surveyor charts faults that move when unobserved.'
const CHAPTER_TITLE = 'Fault Lines'
const SCENE_TITLE = 'Quiet Vault'

let tempRoot = null
let backend = null
let vite = null
let browser = null

function step(message) {
  console.log('[wiki-failure] ' + message)
}

async function clickNavButton(page, name) {
  await page.locator('.sidebar nav.nav button', { hasText: name }).first().click()
}

/** Poll an API predicate by repeatedly issuing the request. */
async function pollApi(client, path, predicate, { timeoutMs = 30000, label } = {}) {
  const deadline = Date.now() + timeoutMs
  let last = null
  while (Date.now() < deadline) {
    last = await client.get(path)
    if (predicate(last)) return last
    await sleep(400)
  }
  throw new Error(
    'Timed out waiting for ' + label + '; last payload: ' + JSON.stringify(last).slice(0, 800),
  )
}

async function run(page) {
  const client = api(BACKEND_PORT)

  // ------------------------------------------------------------------
  // Seed project + chapter + scene through the UI (cheap forms).
  // ------------------------------------------------------------------
  step('create project ' + PROJECT_TITLE)
  await page.goto(vite.url + '/')
  await page.getByRole('button', { name: 'Open project' }).click()
  await page.getByText('Create new project', { exact: true }).click()
  await page.getByPlaceholder('The Glass City').fill(PROJECT_TITLE)
  await page.getByPlaceholder(/disgraced cartographer discovers/).fill(PROJECT_PREMISE)
  await page.getByRole('button', { name: 'Create Project' }).click()
  await page.locator('.topbar h2', { hasText: PROJECT_TITLE }).waitFor({ state: 'visible' })

  const projects = await client.get('/projects')
  const project = projects.find((item) => item.title === PROJECT_TITLE)
  assert.ok(project, 'project created')

  step('create chapter + scene contract')
  await clickNavButton(page, 'Manuscript')
  await page.getByRole('button', { name: 'New Chapter' }).click()
  await page.locator('.chapter-editor input[type="number"]').fill('1')
  await page
    .locator('.chapter-editor label', { hasText: 'Title' })
    .locator('input')
    .fill(CHAPTER_TITLE)
  await page
    .locator('.chapter-editor label', { hasText: 'Summary' })
    .locator('textarea')
    .fill('The ground opens where the map says it cannot.')
  await page.getByRole('button', { name: 'Create Chapter' }).click()
  await page
    .locator('.chapter-list button', { hasText: 'Chapter 1: ' + CHAPTER_TITLE })
    .waitFor({ state: 'visible' })

  await page.getByRole('button', { name: 'New Scene' }).click()
  await page.locator('.scene-editor select').selectOption({ label: 'Chapter 1: ' + CHAPTER_TITLE })
  await page.locator('.scene-editor input[type="number"]').nth(0).fill('1')
  await page.getByPlaceholder('The map changes').fill(SCENE_TITLE)
  await page.getByPlaceholder('Lin Ye').fill('Iva')
  const sceneTextareas = page.locator('.scene-editor textarea')
  await sceneTextareas.nth(0).fill('Photograph the vault floor.') // Goal
  await sceneTextareas.nth(1).fill('The fault swallows the tripod.') // Conflict
  await sceneTextareas.nth(2).fill('The vault breathes back.') // Turning Point
  await page.getByRole('button', { name: 'Create Scene', exact: true }).click()
  await page
    .locator('.scene-list button', { hasText: '1. ' + SCENE_TITLE })
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // Create + accept the manuscript proposal. Core commit lands first;
  // the inline outbox dispatch then fails the two wiki-rooted jobs.
  // ------------------------------------------------------------------
  step('create and accept the manuscript proposal (wiki writes will fail)')
  await page.getByRole('button', { name: 'Create Proposal', exact: true }).click()
  await page
    .locator('.proposal-workspace .proposal-detail h4', { hasText: '1. ' + SCENE_TITLE })
    .waitFor({ state: 'visible' })
  await page
    .locator('.proposal-workspace .proposal-detail')
    .getByRole('button', { name: 'Accept · 保存并分析', exact: true })
    .click()

  // Core data MUST persist despite the failed indexing.
  step('verify Version 1 persisted although indexing failed')
  await page
    .getByText('Chapter 1: ' + CHAPTER_TITLE + ' / Version 1')
    .first()
    .waitFor({ state: 'visible' })

  const revisions = await client.get('/projects/' + project.id + '/manuscript/revisions')
  assert.equal(revisions.length, 1, 'exactly one revision was committed')
  assert.equal(revisions[0].version, 1)
  const scenes = await client.get('/projects/' + project.id + '/manuscript/scenes')
  assert.equal(scenes.length, 1)
  assert.equal(scenes[0].version, 1)

  // Outbox truth: wiki ingest + writeback analysis failed, consistency passed.
  step('inspect outbox job outcomes')
  const jobs = await pollApi(
    client,
    '/projects/' + project.id + '/outbox-jobs',
    (list) => {
      const revisionJobs = list.filter((job) => job.aggregate_id === revisions[0].id)
      return revisionJobs.length === 4 && revisionJobs.every((job) => ['succeeded', 'failed'].includes(job.status))
    },
    { label: 'all four revision jobs to reach a terminal status' },
  )
  const byType = Object.fromEntries(jobs.filter((job) => job.aggregate_id === revisions[0].id).map((job) => [job.job_type, job]))
  assert.equal(byType.llm_wiki_ingest.status, 'failed', 'wiki ingestion job failed')
  assert.equal(byType.writeback_analysis.status, 'failed', 'write-back analysis job failed (memplace writes under the blocked projects root)')
  assert.match(byType.llm_wiki_ingest.last_error || '', /NotADirectoryError|FileExistsError|ENOTDIR|Error/, 'wiki failure carries an error message')
  assert.equal(byType.consistency_analysis.status, 'succeeded', 'DB-only analysis still succeeded')

  // The Manuscript workspace surfaces the FAILED analysis job with a Retry button.
  const failedArticle = page
    .locator('.post-accept-analysis article')
    .filter({ hasText: 'Write-back suggestions' })
    .first()
  await failedArticle.waitFor({ state: 'visible' })
  await failedArticle.locator('.severity-chip', { hasText: 'failed' }).waitFor({ state: 'visible' })
  await failedArticle.getByRole('button', { name: 'Retry' }).waitFor({ state: 'visible' })
  assert.ok(
    await failedArticle.locator('.error-text').isVisible(),
    'the failed job shows its error text',
  )
  await page
    .locator('.post-accept-analysis article')
    .filter({ hasText: 'Consistency report' })
    .locator('.severity-chip', { hasText: 'succeeded' })
    .waitFor({ state: 'visible' })

  // ------------------------------------------------------------------
  // Remove the blocker and Retry from the UI.
  // ------------------------------------------------------------------
  step('remove the blocking file and trigger Retry from the UI')
  await unlink(join(tempRoot, 'projects'))

  await failedArticle.getByRole('button', { name: 'Retry' }).click()

  await failedArticle
    .locator('.severity-chip', { hasText: 'succeeded' })
    .waitFor({ state: 'visible', timeout: 60000 })

  const retried = await client.get('/projects/' + project.id + '/outbox-jobs')
  const retriedByType = Object.fromEntries(retried.filter((job) => job.aggregate_id === revisions[0].id).map((job) => [job.job_type, job]))
  assert.equal(
    retriedByType.writeback_analysis.status,
    'succeeded',
    'retried write-back analysis job now succeeds',
  )

  // ------------------------------------------------------------------
  // Retry the failed wiki index job from the UI as well.
  // ------------------------------------------------------------------
  step('retry the failed wiki index job from the UI')
  const wikiArticle = page
    .locator('.post-accept-analysis article')
    .filter({ hasText: 'Wiki index' })
    .first()
  await wikiArticle.locator('.severity-chip', { hasText: 'failed' }).waitFor({ state: 'visible' })
  await wikiArticle.getByRole('button', { name: 'Retry' }).click()
  await wikiArticle
    .locator('.severity-chip', { hasText: 'succeeded' })
    .waitFor({ state: 'visible', timeout: 60000 })

  const retriedAgain = await client.get('/projects/' + project.id + '/outbox-jobs')
  const retriedAgainByType = Object.fromEntries(retriedAgain.filter((job) => job.aggregate_id === revisions[0].id).map((job) => [job.job_type, job]))
  assert.equal(
    retriedAgainByType.llm_wiki_ingest.status,
    'succeeded',
    'retried wiki index job now succeeds',
  )

  // Wiki-side write path really recovered: the memplace prose sample landed
  // under <root>/projects/<project>/modules/memplace/prose_samples/ and the
  // retried ingest staged wiki sources under modules/llm_wiki/sources/.
  const samplesDir = join(tempRoot, 'projects', project.id, 'modules', 'memplace', 'prose_samples')
  const sampleFiles = existsSync(samplesDir) ? readdirSync(samplesDir) : []
  assert.ok(
    sampleFiles.some((name) => name.endsWith('.md')),
    'retried job wrote the prose sample into the recovered wiki root (' + samplesDir + ')',
  )
  const wikiSourcesDir = join(tempRoot, 'projects', project.id, 'modules', 'llm_wiki', 'sources')
  assert.ok(
    existsSync(wikiSourcesDir),
    'retried ingest staged wiki sources into the recovered root (' + wikiSourcesDir + ')',
  )

  // ------------------------------------------------------------------
  // No duplicate manuscript versions were created anywhere along the way.
  // ------------------------------------------------------------------
  step('assert no duplicate manuscript versions')
  const revisionsAfterRetry = await client.get('/projects/' + project.id + '/manuscript/revisions')
  assert.equal(revisionsAfterRetry.length, 1, 'still exactly one revision after the retry')
  assert.equal(revisionsAfterRetry[0].version, 1)
  const scenesAfterRetry = await client.get('/projects/' + project.id + '/manuscript/scenes')
  assert.equal(scenesAfterRetry.length, 1, 'still exactly one accepted manuscript scene')
  assert.equal(scenesAfterRetry[0].version, 1)

  assert.equal(
    await page.locator('.accepted-manuscript .accepted-item').count(),
    1,
    'Accepted Manuscript panel renders exactly one scene',
  )
  assert.equal(
    await page.locator('.revision-history .revision-item').count(),
    1,
    'Revision History renders exactly one revision',
  )
}

async function main() {
  tempRoot = await mkTempRoot('ai-writing-e2e-wikifail-')
  // Force the failure BEFORE the backend boots: a plain file named 'projects'.
  await blockWikiRootWithFile(tempRoot)
  console.log('[wiki-failure] temp data root (with blocking file): ' + tempRoot)
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
    console.log('[wiki-failure] PASS')
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
