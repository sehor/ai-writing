import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { fileURLToPath } from 'node:url'
import {
  api,
  launchBrowser,
  mkTempRoot,
  reportFailure,
  rmTempRoot,
  startBackend,
  startVite,
  stopBackend,
  stopVite,
} from './lib/harness.mjs'

async function freePort() {
  const server = createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}

const dataRoot = await mkTempRoot('ai-writing-e2e-narrative-maintenance-')
let backend, vite, browser
try {
  const backendPort = await freePort()
  backend = await startBackend({ port: backendPort, dataRoot })
  vite = await startVite({ port: await freePort(), backendPort })
  const client = api(backendPort)
  const project = await client.post('/projects', { title: '时态事实验收', premise: '一封信隐藏了未来真相。' })
  const base = `/projects/${project.id}`
  const scene = await client.post(`${base}/scene-contracts`, {
    sequence: 4,
    title: '第四场',
    pov: '林舟',
    goal: '确认信件作者',
    conflict: '证据不完整',
  })

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
  await page.getByRole('button', { name: '故事设定', exact: true }).click()
  await page.getByRole('region', { name: '时态事实与知识' }).waitFor()

  async function createFact({ subject, predicate, value, start, end, readerFrom, source }) {
    await page.getByRole('button', { name: '新建事实', exact: true }).click()
    const editor = page.getByRole('region', { name: '事实编辑器' })
    await editor.getByLabel('主体').fill(subject)
    await editor.getByLabel('关系 / 属性').fill(predicate)
    await editor.getByLabel('事实内容').fill(value)
    await editor.getByLabel('有效起始场景').fill(String(start))
    if (end !== null) await editor.getByLabel('有效结束场景').fill(String(end))
    if (readerFrom !== null) await editor.getByLabel('读者可见场景').fill(String(readerFrom))
    await editor.getByLabel('来源').fill(source)
    const response = page.waitForResponse(res => res.url().endsWith('/story-facts') && res.request().method() === 'POST')
    await editor.getByRole('button', { name: '保存事实', exact: true }).click()
    assert.equal((await response).status(), 201)
    await page.getByText('事实已保存为 v1。', { exact: true }).waitFor()
    return (await client.get(`${base}/story-facts`)).find(item => item.value === value)
  }

  const current = await createFact({
    subject: '信件', predicate: '作者', value: 'CURRENT_TRUTH_AUD19',
    start: 1, end: 5, readerFrom: 2, source: 'scene:four',
  })
  assert.ok(current, 'current fact created through the UI')

  await page.getByRole('button', { name: '新建角色知识', exact: true }).click()
  const knowledgeEditor = page.getByRole('region', { name: '知识状态编辑器' })
  await knowledgeEditor.getByRole('textbox', { name: '角色', exact: true }).fill('林舟')
  await knowledgeEditor.getByLabel('知情起始场景').fill('4')
  await knowledgeEditor.getByLabel('来源').fill('scene:four')
  await knowledgeEditor.getByLabel('维护原因').fill('林舟在第四场亲眼确认')
  const knowledgeResponse = page.waitForResponse(res => res.url().includes(`/story-facts/${current.id}/knowledge-states`) && res.request().method() === 'POST')
  await knowledgeEditor.getByRole('button', { name: '保存知识状态', exact: true }).click()
  assert.equal((await knowledgeResponse).status(), 201)
  await page.getByText('知识状态已保存为 v1。', { exact: true }).waitFor()

  const futureSecret = 'FUTURE_SECRET_AUD19'
  const future = await createFact({
    subject: '信件', predicate: '真正目的', value: futureSecret,
    start: 8, end: null, readerFrom: 10, source: 'author:future-outline',
  })
  assert.ok(future, 'future fact created through the UI')
  assert.ok((await page.getByTestId('fact-list').innerText()).includes(futureSecret), 'author management can see future information')

  await page.getByLabel('预览场景').selectOption('4')
  await page.getByLabel('预览角色').fill('林舟')
  const previewResponse = page.waitForResponse(res => res.url().includes('/story-state?scene_position=4') && res.request().method() === 'GET')
  await page.getByRole('button', { name: '预览场景知识', exact: true }).click()
  assert.equal((await previewResponse).status(), 200)
  const preview = page.getByRole('region', { name: '场景知识预览' })
  await preview.getByText('CURRENT_TRUTH_AUD19', { exact: true }).first().waitFor()
  const previewText = await preview.innerText()
  assert.ok(previewText.includes('世界真相'))
  assert.ok(previewText.includes('读者已知'))
  assert.ok(previewText.includes('林舟已知'))
  assert.ok(previewText.includes('scene:four'))
  assert.ok(!previewText.includes(futureSecret), 'future secret stays out of scene 4 preview')

  const suggestion = await client.post(`${base}/references/suggestions/generate`, {
    suggestion_type: 'brainstorm',
    scope_type: 'scene',
    scope_ref: scene.id,
    author_problem: '基于当前安全知识给出一个不剧透的写作方向。',
  })
  assert.ok(suggestion.used_context.includes('CURRENT_TRUTH_AUD19'), 'current safe fact reaches real generation context')
  assert.ok(!suggestion.used_context.includes(futureSecret), 'future secret does not leak into real generation context')

  await page.getByTestId('fact-list').getByRole('button', { name: /CURRENT_TRUTH_AUD19/ }).click()
  const correctionEditor = page.getByRole('region', { name: '事实编辑器' })
  await correctionEditor.getByLabel('事实内容').fill('CURRENT_TRUTH_AUD19_CORRECTED')
  await correctionEditor.getByLabel('更正原因').fill('作者复核原始信件')
  const correctionResponse = page.waitForResponse(res => res.url().endsWith(`/story-facts/${current.id}`) && res.request().method() === 'PUT')
  await correctionEditor.getByRole('button', { name: '保存更正', exact: true }).click()
  assert.equal((await correctionResponse).status(), 200)
  await page.getByText('事实已保存为 v2。', { exact: true }).waitFor()
  assert.equal((await client.get(`${base}/story-facts`)).find(item => item.id === current.id)?.value, 'CURRENT_TRUTH_AUD19_CORRECTED')

  await page.screenshot({ path: fileURLToPath(new URL('../.tmp/narrative-maintenance.png', import.meta.url)), fullPage: true })
  assert.deepEqual(errors, [])
  console.log('PASS: UI fact/knowledge maintenance feeds scene-safe preview while future information remains author-only and is excluded from generation context.')
} catch (error) {
  reportFailure(error, [backend, vite])
  process.exitCode = 1
} finally {
  await browser?.close()
  await stopVite(vite)
  await stopBackend(backend)
  await rmTempRoot(dataRoot)
}
