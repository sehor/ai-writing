import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { api, launchBrowser, mkTempRoot, pollUntil, reportFailure, rmTempRoot, startBackend, startVite, stopBackend, stopVite, REPO_ROOT } from './lib/harness.mjs'

async function freePort() {
  const server = createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}
const dataRoot = await mkTempRoot('ai-writing-e2e-structured-')
let backend, vite, browser
try {
  const backendPort = await freePort()
  backend = await startBackend({ port: backendPort, dataRoot })
  vite = await startVite({ port: await freePort(), backendPort })
  const client = api(backendPort)
  // Project creation is real API setup; chapter, scene, generation and acceptance are UI actions.
  const project = await client.post('/projects', { title: '结构化起草完整验收', premise: '一名修复师追查雾港旧信。' })
  const base = `/projects/${project.id}`
  browser = await launchBrowser()
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  page.setDefaultTimeout(15000)
  page.on('dialog', dialog => dialog.accept())
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(vite.url)
  await page.locator('.project-dialog-trigger').click()
  await page.locator('.project-picker-list button', { hasText: project.title }).click()
  await page.locator('.project-dialog').waitFor({ state: 'hidden' })
  await page.locator('.workspace-content[aria-busy="false"]').waitFor()
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  await page.getByRole('button', { name: '管理章节与场景', exact: true }).click()
  const chapterForm = page.locator('.chapter-editor')
  await chapterForm.getByLabel('章节序号', { exact: true }).fill('1')
  await chapterForm.getByLabel('标题', { exact: true }).fill('雾港')
  const chapterResponse = page.waitForResponse(res => res.url().endsWith('/manuscript/chapters') && res.request().method() === 'POST')
  await chapterForm.getByRole('button', { name: '创建章节', exact: true }).click()
  const chapterResult = await chapterResponse
  assert.equal(chapterResult.status(), 201)
  const chapter = await chapterResult.json()
  await page.getByRole('button', { name: '新建场景', exact: true }).click()
  const form = page.locator('.scene-editor')
  await form.getByRole('combobox').selectOption(chapter.id)
  await form.getByLabel('顺序', { exact: true }).fill('1')
  await form.getByLabel('标题', { exact: true }).fill('灯塔下的信')
  await form.getByLabel('叙述视角', { exact: true }).fill('修复师')
  await form.getByLabel('目标', { exact: true }).fill('找到信的主人')
  await form.getByLabel('冲突', { exact: true }).fill('地址已经消失')
  await form.getByLabel('转折点', { exact: true }).fill('发现第二枚邮戳')
  await form.getByLabel('结果与转折', { exact: true }).fill('决定暂时保存信件')
  await form.getByLabel('信息变化', { exact: true }).fill('发现两个不同的寄信日期')
  await form.getByLabel('人物状态变化', { exact: true }).fill('从迟疑转为谨慎调查')
  const sceneResponse = page.waitForResponse(res => res.url().endsWith('/scene-contracts') && res.request().method() === 'POST')
  await form.getByRole('button', { name: '创建场景', exact: true }).click()
  const sceneResult = await sceneResponse
  assert.equal(sceneResult.status(), 201)
  const scene = await sceneResult.json()
  const generatedResponse = page.waitForResponse(res => res.url().endsWith(`/manuscript/proposals/from-scene/${scene.id}`) && res.request().method() === 'POST')
  await form.getByRole('button', { name: '创建草稿', exact: true }).click()
  const generated = await generatedResponse
  assert.equal(generated.status(), 201)
  const proposal = await generated.json()
  for (const plan of ['发现两个不同的寄信日期', '从迟疑转为谨慎调查', '决定暂时保存信件']) assert.ok(proposal.context.includes(plan))
  assert.deepEqual(await client.get(`${base}/manuscript/scenes`), [])
  const draft = page.getByRole('textbox', { name: 'AI 草稿正文', exact: true })
  const authored = '潮水退去，修复师在灯塔下找到旧信。她看见第二枚邮戳，决定暂时保管它。'
  await draft.fill(authored)
  // Leaving explicitly cancels, discards, or persists only the local proposal draft.
  await page.getByRole('button', { name: '雪花规划', exact: true }).click()
  await page.getByRole('dialog', { name: '保存草稿后离开？' }).waitFor()
  await mkdir(join(REPO_ROOT, '.tmp'), { recursive: true })
  await page.screenshot({ path: join(REPO_ROOT, '.tmp', 'proposal-leave.png') })
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.equal(await draft.inputValue(), authored)
  await page.getByRole('button', { name: '雪花规划', exact: true }).click()
  await page.getByRole('button', { name: '不保存并离开', exact: true }).click()
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  assert.equal(await draft.inputValue(), proposal.content)
  await draft.fill(authored)
  await page.getByRole('button', { name: '雪花规划', exact: true }).click()
  await page.getByRole('button', { name: '保存草稿并离开', exact: true }).click()
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  assert.equal(await draft.inputValue(), authored)
  await draft.press('Control+s')
  assert.deepEqual(await client.get(`${base}/manuscript/scenes`), [])
  await page.reload()
  await draft.waitFor()
  assert.equal(await draft.inputValue(), authored)
  let releaseAcceptance
  const acceptanceGate = new Promise(resolve => { releaseAcceptance = resolve })
  let sawAcceptance
  const acceptanceStarted = new Promise(resolve => { sawAcceptance = resolve })
  await page.route('**/manuscript/proposals/*/accept', async route => {
    sawAcceptance(); await acceptanceGate; await route.continue()
  })
  await page.getByRole('button', { name: '接受草稿并分析', exact: true }).click()
  await acceptanceStarted
  await page.getByRole('button', { name: '雪花规划', exact: true }).click()
  assert.equal(await draft.inputValue(), authored)
  assert.equal(await page.locator('.project-dialog-trigger').isDisabled(), true)
  releaseAcceptance()
  const editor = page.getByRole('textbox', { name: '正文内容', exact: true })
  await editor.waitFor()
  assert.equal(await editor.inputValue(), authored)
  const revisions = await client.get(`${base}/manuscript/revisions`)
  assert.equal(revisions.length, 1)
  assert.equal(revisions[0].version, 1)
  assert.equal((await client.get(`${base}/manuscript/proposals`))[0].content, proposal.content)
  await pollUntil(async () => (await client.get(`${base}/outbox-jobs`)).every(job => ['succeeded', 'failed'].includes(job.status)), { label: 'derived jobs settle before orderly backend restart', timeoutMs: 60000 })
  await page.goto('about:blank')
  await stopBackend(backend)
  backend = await startBackend({ port: backendPort, dataRoot })
  await page.goto(vite.url)
  await editor.waitFor()
  assert.equal(await editor.inputValue(), authored)
  assert.deepEqual(await client.get(`${base}/manuscript/revisions`), revisions)
  assert.equal((await client.get(`${base}/scene-contracts`))[0].id, scene.id)
  assert.deepEqual(errors, [])
  console.log('PASS A: UI chapter/scene authoring, complete plan to local generation, draft refresh, explicit acceptance and backend restart preserve author text and revision IDs.')
} catch (error) {
  reportFailure(error, [backend, vite])
  process.exitCode = 1
} finally {
  await browser?.close()
  await stopVite(vite)
  await stopBackend(backend)
  await rmTempRoot(dataRoot)
}
