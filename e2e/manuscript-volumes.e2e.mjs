import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { fileURLToPath } from 'node:url'
import { api, launchBrowser, mkTempRoot, reportFailure, rmTempRoot, startBackend, startVite, stopBackend, stopVite } from './lib/harness.mjs'

async function freePort() {
  const server = createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}
const dataRoot = await mkTempRoot('ai-writing-e2e-volumes-')
let backend, vite, browser
try {
  const backendPort = await freePort()
  backend = await startBackend({ port: backendPort, dataRoot })
  vite = await startVite({ port: await freePort(), backendPort })
  const client = api(backendPort)
  const project = await client.post('/projects', { title: '卷组织验收', premise: '一封信贯穿两卷。' })
  const other = await client.post('/projects', { title: '另一部作品', premise: '不能混入旧卷。' })
  const base = `/projects/${project.id}`
  const chapters = [], scenes = []
  for (let sequence = 1; sequence <= 2; sequence++) {
    const chapter = await client.post(`${base}/manuscript/chapters`, { sequence, title: `章节${sequence}` })
    chapters.push(chapter)
    const scene = await client.post(`${base}/scene-contracts`, { sequence, chapter_id: chapter.id, title: `场景${sequence}`, goal: '找到寄信人', pov: '林舟' })
    scenes.push(scene)
    const proposal = await client.post(`${base}/manuscript/proposals/from-scene/${scene.id}`)
    await client.put(`${base}/manuscript/proposals/${proposal.id}/status`, { status: 'accepted' })
  }
  const before = await client.get(`${base}/manuscript/revisions`)
  browser = await launchBrowser()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.setDefaultTimeout(15000)
  page.on('dialog', dialog => dialog.accept())
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  async function pick(title) {
    await page.locator('.project-dialog-trigger').click()
    await page.locator('.project-picker-list button', { hasText: title }).click()
    await page.locator('.project-dialog').waitFor({ state: 'hidden' })
    await page.locator('.workspace-content[aria-busy="false"]').waitFor()
  }
  await page.goto(vite.url)
  await pick(project.title)
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  await page.getByRole('button', { name: '管理章节与场景', exact: true }).click()
  const manager = page.getByRole('region', { name: '卷组织', exact: true })
  async function save(title, sequence) {
    await manager.getByLabel('卷名', { exact: true }).fill(title)
    await manager.getByLabel('卷排序号', { exact: true }).fill(String(sequence))
    const response = page.waitForResponse(res => res.url().includes('/manuscript/volumes') && ['POST', 'PUT'].includes(res.request().method()))
    await manager.getByRole('button', { name: '保存卷', exact: true }).click()
    const result = await response
    assert.ok(result.ok())
    return result.json()
  }
  const lower = await save('下卷', 2)
  await manager.getByLabel('选择卷', { exact: true }).selectOption('')
  const upper = await save('上卷', 1)
  await manager.getByText('章节归卷（保存后立即生效）', { exact: true }).click()
  async function assign(chapter, volume) {
    const response = page.waitForResponse(res => res.url().endsWith(`/chapters/${chapter.id}/volume`) && res.request().method() === 'PUT')
    await manager.getByLabel(`章节《${chapter.title}》所属卷`, { exact: true }).selectOption(volume)
    assert.equal((await response).status(), 200)
  }
  await assign(chapters[0], lower.id)
  await assign(chapters[1], upper.id)
  await save('上卷 · 归途', 1)
  const directory = page.locator('.chapter-directory')
  await directory.locator(`[data-volume-id="${upper.id}"] .scene-link`, { hasText: '场景2' }).waitFor()
  assert.deepEqual(await directory.locator('.volume-group').evaluateAll(elements => elements.map(el => el.dataset.volumeId)), [upper.id, lower.id])
  const exported = await client.get(`${base}/manuscript/export`)
  assert.ok(exported.content.indexOf('上卷 · 归途') < exported.content.indexOf('下卷'))
  assert.ok(exported.content.includes(before[0].content))

  await manager.getByLabel('卷名', { exact: true }).fill('恢复我的卷草稿')
  await page.reload()
  await page.getByRole('button', { name: '管理章节与场景', exact: true }).click()
  await manager.getByLabel('选择卷', { exact: true }).selectOption(upper.id)
  assert.equal(await manager.getByLabel('卷名', { exact: true }).inputValue(), '恢复我的卷草稿')
  await save('上卷 · 归途', 1)
  await pick(other.title)
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  await page.getByRole('button', { name: '管理章节与场景', exact: true }).click()
  assert.equal(await manager.getByLabel('选择卷', { exact: true }).locator('option').count(), 1)
  await pick(project.title)
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  if (!await manager.isVisible()) await page.getByRole('button', { name: '管理章节与场景', exact: true }).click()
  await manager.getByLabel('选择卷', { exact: true }).selectOption(upper.id)
  await manager.getByText('章节归卷（保存后立即生效）', { exact: true }).click()
  await assign(chapters[0], upper.id)
  await assign(chapters[0], '')
  await manager.getByRole('button', { name: '删除卷，保留章节', exact: true }).click()
  await directory.locator('[data-volume-id=""] .scene-link', { hasText: '场景2' }).waitFor()
  assert.deepEqual(await client.get(`${base}/manuscript/revisions`), before)
  assert.deepEqual((await client.get(`${base}/scene-contracts`)).map(scene => scene.id), scenes.map(scene => scene.id))
  await page.screenshot({ path: fileURLToPath(new URL('../.tmp/manuscript-volumes.png', import.meta.url)), fullPage: true })
  assert.deepEqual(errors, [])
  console.log('PASS: volume creation, rename/order, membership movement, reload draft recovery and project isolation; deleting volumes preserves chapters, scenes and prose history.')
} catch (error) {
  reportFailure(error, [backend, vite])
  process.exitCode = 1
} finally {
  await browser?.close()
  await stopVite(vite)
  await stopBackend(backend)
  await rmTempRoot(dataRoot)
}
