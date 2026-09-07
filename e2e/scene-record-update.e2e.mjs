import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { api, launchBrowser, mkTempRoot, pollUntil, reportFailure, rmTempRoot, startBackend, startVite, stopBackend, stopVite } from './lib/harness.mjs'

async function freePort() {
  const server = createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}

const dataRoot = await mkTempRoot('ai-writing-e2e-record-update-')
let backend, vite, browser
try {
  const backendPort = await freePort()
  backend = await startBackend({ dataRoot, port: backendPort })
  vite = await startVite({ port: await freePort(), backendPort })
  const client = api(backendPort)
  const project = await client.post('/projects', { title: 'Record update review', premise: 'A gate opens.' })
  const base = `/projects/${project.id}`
  const payload = { title: 'Opening', pov: 'Mira', goal: 'Open the gate', conflict: 'The lock resists', turning_point: 'The key fits',
    outcome: 'The gate opens', required_canon_ids: [], forbidden_facts: [], information_delta: 'The key works', character_state_delta: 'Mira enters', story_thread_actions: [] }
  const record = await client.post(`${base}/snowflake/record-revisions`, { step_number: 8, record_id: 'scene-opening', position: 1, payload })
  await client.post(`${base}/snowflake/record-revisions/${record.id}/decisions`, { decision: 'accepted', expected_revision_id: '' })
  const initial = await client.post(`${base}/snowflake/records/8/parse-scene-proposals`)
  const accepted = await client.post(`${base}/snowflake/scene-proposals/accept`, { proposal_ids: initial.proposals.map(p => p.id) })
  const scene = accepted.scenes[0]
  const prose = await client.post(`${base}/manuscript/proposals/from-scene/${scene.id}`)
  await client.put(`${base}/manuscript/proposals/${prose.id}/status`, { status: 'accepted' })
  const history = await client.get(`${base}/manuscript/revisions`)
  browser = await launchBrowser()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.setDefaultTimeout(15000)
  page.on('dialog', dialog => dialog.accept())
  await page.goto(vite.url)
  await page.locator('.project-dialog-trigger').click()
  await page.locator('.project-picker-list button', { hasText: project.title }).click()
  await page.locator('.project-dialog').waitFor({ state: 'hidden' })
  await page.locator('.workspace-content[aria-busy="false"]').waitFor()
  await page.getByRole('button', { name: '雪花规划', exact: true }).click()
  await page.getByRole('button', { name: /^Open step 8:/ }).click()
  await page.locator('.record-list-item button').first().click()
  await page.getByLabel('结构化数据', { exact: true }).fill(JSON.stringify({ ...payload, outcome: 'REVISED OUTCOME' }))
  await page.getByRole('button', { name: '保存记录草稿', exact: true }).click()
  await page.getByRole('button', { name: '接受', exact: true }).click()
  await page.getByRole('button', { name: '解析场景建议', exact: true }).click()
  const diff = page.locator('.scene-update-review')
  await diff.getByText('更新原场景 · 核对差异', { exact: true }).click()
  assert.ok((await diff.innerText()).includes('REVISED OUTCOME'))
  // Another editor changes the target after compilation. The UI must reject
  // the stale proposal, then show that manual title in the fresh differences.
  await client.put(`${base}/scene-contracts/${scene.id}`, { ...scene, title: 'Manual title' })
  await page.getByRole('button', { name: '接受全部待审场景', exact: true }).click()
  await page.getByText('场景或来源已变化，请重新解析并核对最新差异。', { exact: true }).waitFor()
  const recompiled = page.waitForResponse(response => response.url().endsWith('/snowflake/records/8/parse-scene-proposals') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '解析场景建议', exact: true }).click()
  assert.equal((await recompiled).status(), 201)
  await page.getByRole('button', { name: '解析场景建议', exact: true }).waitFor()
  await diff.getByText('更新原场景 · 核对差异', { exact: true }).click()
  assert.ok((await diff.innerText()).includes('Manual title'))
  await page.getByRole('button', { name: '接受全部待审场景', exact: true }).click()
  await pollUntil(async () => (await client.get(`${base}/scene-contracts`))[0].outcome.includes('REVISED OUTCOME'), { label: 'scene plan updated' })
  const updated = await client.get(`${base}/scene-contracts`)
  assert.equal(updated.length, 1)
  assert.equal(updated[0].id, scene.id)
  assert.deepEqual(await client.get(`${base}/manuscript/revisions`), history)
  assert.ok(updated[0].manuscript_plan_version < updated[0].plan_version)
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  await page.getByText('规划已更新，正文待核对', { exact: true }).waitFor()
  console.log('PASS: Step 8 edit, reviewable update, target conflict, recompile, stable scene/history and stale prose indicator.')
} catch (error) {
  reportFailure(error, [backend, vite])
  process.exitCode = 1
} finally {
  await browser?.close()
  await stopVite(vite)
  await stopBackend(backend)
  await rmTempRoot(dataRoot)
}
