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
const dataRoot = await mkTempRoot('ai-writing-e2e-copilot-')
let backend, vite, browser
try {
  const backendPort = await freePort()
  backend = await startBackend({ port: backendPort, dataRoot })
  vite = await startVite({ port: await freePort(), backendPort })
  const client = api(backendPort)
  const project = await client.post('/projects', { title: '选区求助验收', premise: '一封信改变人物的决定。' })
  const base = `/projects/${project.id}`
  const scene = await client.post(`${base}/scene-contracts`, { sequence: 1, title: '信件', goal: '找到寄信人', pov: '林舟' })
  const proposal = await client.post(`${base}/manuscript/proposals/from-scene/${scene.id}`)
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
  await page.getByRole('button', { name: /待审核草稿/ }).click()
  const draft = page.getByRole('textbox', { name: 'AI 草稿正文' })
  const unsaved = '林舟😀停在信箱前。他不敢伸手。'
  async function selectAndAsk(editor) {
    await editor.fill(unsaved)
    await editor.evaluate(element => { element.focus(); element.setSelectionRange(4, 9); element.dispatchEvent(new Event('select', { bubbles: true })) })
    await page.getByRole('button', { name: '就选中文字求助', exact: true }).click()
    await page.getByLabel('求助原文').waitFor()
    await page.getByLabel('写作问题', { exact: true }).fill('让停顿更自然，保持当前人物视角。')
    const response = page.waitForResponse(res => res.url().endsWith('/references/suggestions/generate') && res.request().method() === 'POST')
    await page.getByRole('button', { name: '生成参考建议', exact: true }).click()
    const result = await response
    assert.equal(result.status(), 201)
    const suggestion = await result.json()
    assert.equal(suggestion.editor_context.selected_text, unsaved.slice(4, 9))
    assert.equal(suggestion.editor_context.snapshot_text, unsaved)
    assert.ok(suggestion.used_context.includes('让停顿更自然'))
    return suggestion
  }
  async function applyAndUndo(editor, replacement) {
    const expected = `${unsaved.slice(0, 4)}${replacement}${unsaved.slice(9)}`
    const applicationText = page.getByRole('textbox', { name: '待应用文本' })
    await applicationText.fill(replacement)
    await page.getByRole('button', { name: '预览应用', exact: true }).click()
    const preview = page.getByLabel('应用预览')
    await preview.waitFor()
    assert.ok((await preview.textContent()).includes(expected))
    assert.equal(await editor.inputValue(), unsaved)
    await page.getByRole('button', { name: '应用到草稿', exact: true }).click()
    assert.equal(await editor.inputValue(), expected)
    await page.getByText('已应用到当前本地草稿，尚未保存正式版本。', { exact: true }).waitFor()
    await page.getByRole('button', { name: '应用到草稿', exact: true }).click()
    await page.getByText('原文、目标、版本或编辑会话已变化，请回到编辑器重新选择。', { exact: true }).waitFor()
    assert.equal(await editor.inputValue(), expected)
    await page.getByRole('button', { name: '撤销上次应用', exact: true }).click()
    assert.equal(await editor.inputValue(), unsaved)
  }
  const first = await selectAndAsk(draft)
  assert.equal(first.editor_context.proposal_id, proposal.id)
  assert.equal(first.editor_context.source_kind, 'proposal_draft')
  assert.equal((await client.get(`${base}/manuscript/proposals`))[0].content, proposal.content)
  assert.deepEqual(await client.get(`${base}/manuscript/scenes`), [])
  await applyAndUndo(draft, '他收回手，屏住呼吸。')
  assert.equal((await client.get(`${base}/manuscript/proposals`))[0].content, proposal.content)
  assert.deepEqual(await client.get(`${base}/manuscript/scenes`), [])
  await draft.fill(unsaved + '新内容')
  await page.getByRole('alert').filter({ hasText: '重新选择' }).waitFor()
  assert.equal(await page.getByRole('button', { name: '生成参考建议', exact: true }).isDisabled(), true)

  // Commit the original proposal through the API, then exercise the independent
  // accepted-manuscript editor against an unsaved local draft.
  await client.put(`${base}/manuscript/proposals/${proposal.id}/status`, { status: 'accepted' })
  await page.reload()
  await page.getByRole('button', { name: '正式正文', exact: true }).click()
  const accepted = page.getByRole('textbox', { name: '正文内容' })
  const second = await selectAndAsk(accepted)
  assert.equal(second.editor_context.source_kind, 'accepted_manuscript')
  assert.equal(second.editor_context.expected_scene_version, 1)
  assert.equal((await client.get(`${base}/manuscript/scenes`))[0].content, proposal.content)
  assert.equal((await client.get(`${base}/manuscript/revisions`)).length, 1)
  await page.getByLabel('待应用文本').fill('他收回手，屏住呼吸。')
  await page.getByRole('button', { name: '预览应用', exact: true }).click()
  await page.getByLabel('应用预览').waitFor()
  await page.locator('.editor-scroll').evaluate(element => { element.scrollTop = 0 })
  await page.screenshot({ path: fileURLToPath(new URL('../.tmp/copilot-reference-apply.png', import.meta.url)), fullPage: true })
  await page.getByRole('button', { name: '应用到草稿', exact: true }).click()
  assert.notEqual(await accepted.inputValue(), unsaved)
  assert.equal((await client.get(`${base}/manuscript/scenes`))[0].content, proposal.content)
  assert.equal((await client.get(`${base}/manuscript/revisions`)).length, 1)
  await page.getByRole('button', { name: '撤销上次应用', exact: true }).click()
  assert.equal(await accepted.inputValue(), unsaved)
  // Undo is a guarded single local operation; a new preview/application is explicit,
  // not a claim that a general Redo stack exists.
  await page.getByRole('button', { name: '预览应用', exact: true }).click()
  await page.getByRole('button', { name: '应用到草稿', exact: true }).click()
  const applied = await accepted.inputValue()
  assert.equal(applied, `${unsaved.slice(0, 4)}他收回手，屏住呼吸。${unsaved.slice(9)}`)
  assert.equal((await client.get(`${base}/manuscript/revisions`)).length, 1)
  await accepted.press('Control+s')
  await page.getByText('已保存 · 版本 2', { exact: true }).waitFor()
  assert.equal((await client.get(`${base}/manuscript/scenes`))[0].content, applied)
  assert.equal((await client.get(`${base}/manuscript/revisions`)).length, 2)
  assert.equal((await client.get(`${base}/references/suggestions`)).find(item => item.id === second.id).status, 'pending_review')
  await page.reload()
  await accepted.waitFor()
  assert.equal(await accepted.inputValue(), applied)
  assert.deepEqual(errors, [])
  console.log('PASS B: scoped suggestions preview/apply/undo only affect local drafts; duplicate/stale protections hold, and only explicit Save creates a persisted new revision without changing suggestion review status.')
} catch (error) {
  reportFailure(error, [backend, vite])
  process.exitCode = 1
} finally {
  await browser?.close()
  await stopVite(vite)
  await stopBackend(backend)
  await rmTempRoot(dataRoot)
}
