import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import {
  api,
  BACKEND_DIR,
  BACKEND_PYTHON,
  launchBrowser,
  mkTempRoot,
  pollUntil,
  reportFailure,
  rmTempRoot,
  startBackend,
  startVite,
  stopBackend,
  stopVite,
} from './lib/harness.mjs'

async function freePort() {
  const server = createServer()
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise((resolve) => server.close(resolve))
  return port
}
const dataRoot = await mkTempRoot('ai-writing-e2e-workspace-')
let backend, vite, browser
try {
  const backendPort = await freePort()
  backend = await startBackend({ dataRoot, port: backendPort })
  vite = await startVite({ port: await freePort(), backendPort })
  const client = api(backendPort)
  const project = await client.post('/projects', {
    title: '写作工作台回归',
    premise: '一名修复师在雾港寻找旧信的主人。',
  })
  const base = `/projects/${project.id}`
  const chapter = await client.post(`${base}/manuscript/chapters`, {
    sequence: 1,
    title: '雾港',
    summary: '第一封信出现。',
  })
  const scene = await client.post(`${base}/scene-contracts`, {
    chapter_id: chapter.id,
    sequence: 1,
    title: '灯塔下的信',
    pov: '修复师',
    goal: '找到信的主人',
    conflict: '地址已沉入海底',
    turning_point: '发现信纸背后的线索',
  })
  // Real service + controlled FakeModelGateway; no external provider or paid calls.
  const proposal = JSON.parse(execFileSync(BACKEND_PYTHON, [
    '-c', 'import runpy,sys; script=sys.argv.pop(1); runpy.run_path(script, run_name="__main__")',
    fileURLToPath(new URL('./lib/generate-review-fixture.py', import.meta.url)), dataRoot, project.id, scene.id,
  ], { cwd: BACKEND_DIR, env: { ...process.env, PYTHONIOENCODING: 'utf-8', AI_WRITING_DATA_ROOT: dataRoot }, encoding: 'utf8' }).trim().split('\n').at(-1))
  browser = await launchBrowser()
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('dialog', (dialog) => dialog.accept())
  page.setDefaultTimeout(15000)
  await page.goto(vite.url)
  await page.locator('.project-dialog-trigger').click()
  await page
    .locator('.project-picker-list button', { hasText: project.title })
    .click()
  await page.locator('.project-dialog').waitFor({ state: 'hidden' })
  await page.locator('.workspace-content[aria-busy="false"]').waitFor()
  await page.getByRole('button', { name: '正文写作', exact: true }).click()
  await page.getByRole('button', { name: /待审核草稿/ }).click()
  const review = page.getByRole('region', { name: '生成审核材料' })
  await review.getByText('暂时保留信件', { exact: true }).waitFor()
  await review.getByLabel('设计偏差 1处理状态').selectOption('reviewed')
  await review.getByLabel('连续性问题 1处理状态').selectOption('question')
  await page.reload()
  await review.getByText('旧邮戳来自哪里？', { exact: true }).waitFor()
  assert.equal(await review.getByLabel('设计偏差 1处理状态').inputValue(), 'reviewed')
  assert.equal(await review.getByLabel('连续性问题 1处理状态').inputValue(), 'question')
  const draft = page.getByRole('textbox', { name: 'AI 草稿正文' })
  await draft.fill('潮水退去后，修复师在灯塔下找到一封信。\n\n她把信留了下来。')
  await draft.press('Control+s')
  assert.equal((await client.get(`${base}/manuscript/scenes`)).length, 0)
  await page
    .getByRole('button', { name: '接受草稿并分析', exact: true })
    .click()
  const editor = page.getByRole('textbox', { name: '正文内容', exact: true })
  await editor.waitFor()
  const accepted = await editor.inputValue()
  assert.ok(accepted.includes('她把信留了下来'))
  assert.equal(
    (await client.get(`${base}/manuscript/proposals`))[0].content,
    proposal.content,
    'AI source remains unchanged',
  )
  await editor.fill(accepted + '\n\n远处传来渡轮的汽笛。')
  await editor.press('Control+s')
  await page.getByText('已保存 · 版本 2', { exact: true }).waitFor()
  assert.equal(
    await editor.evaluate((el) => el === document.activeElement),
    true,
  )
  const saved = await client.get(`${base}/manuscript/scenes`)
  assert.equal(saved[0].version, 2)
  await page.getByRole('button', { name: '版本历史', exact: true }).click()
  await page.locator('.revision-history').waitFor()
  await pollUntil(
    async () => {
      const jobs = await client.get(`${base}/outbox-jobs`)
      return (
        jobs.length >= 4 &&
        jobs.every((job) => ['succeeded', 'failed'].includes(job.status))
      )
    },
    { label: 'post-commit analysis reaches terminal state', timeoutMs: 60000 },
  )
  assert.ok((await client.get(`${base}/manuscript/revisions`)).length >= 2)
  await page.getByRole('button', { name: '关闭辅助面板' }).click()
  await page.getByRole('button', { name: '导出 Markdown', exact: true }).click()
  await page.locator('.export-output pre').waitFor()
  assert.ok(
    (await page.locator('.export-output pre').innerText()).includes('汽笛'),
  )
  // Concurrent author: update through the API, then prove the editor protects
  // the stale draft, requires acknowledgment and uses the new version.
  await editor.fill('作者尚未保存的新段落。')
  await client.put(`${base}/manuscript/scenes/${scene.id}`, {
    title: scene.title,
    content: '另一个窗口保存的正文。',
    expected_scene_version: 2,
  })
  await editor.press('Control+s')
  const conflict = page.getByRole('region', { name: '正文版本冲突' })
  await conflict.waitFor()
  assert.equal(await editor.inputValue(), '作者尚未保存的新段落。')
  await conflict
    .getByRole('button', { name: '已核对当前正文，保留我的编辑' })
    .click()
  await editor.press('Control+s')
  await page.getByText('已保存 · 版本 4', { exact: true }).waitFor()
  await page.reload()
  await editor.waitFor()
  assert.equal(await editor.inputValue(), '作者尚未保存的新段落。')
  await page.getByRole('button', { name: '分析与回写', exact: true }).click()
  await page.locator('.writeback-review').waitFor()
  await client.post(`${base}/writeback/proposals`, {
    target: 'canon_entity',
    action: 'create',
    title: '确认灯塔的位置',
    rationale: '作者审核后的已知事实',
    payload: {
      entity_type: 'location',
      name: '旧灯塔',
      summary: '位于雾港入口。',
      current_state: '仍在使用',
      constraints: '',
      last_seen: '',
      timeline_notes: '',
    },
  })
  await page
    .locator('.writeback-review')
    .getByRole('button', { name: '刷新', exact: true })
    .click()
  await page
    .locator('.writeback-review .proposal-list button', {
      hasText: '确认灯塔的位置',
    })
    .click()
  await page
    .locator('.writeback-review .proposal-detail')
    .getByRole('button', { name: '接受', exact: true })
    .click()
  await page.getByText('变更已接受并应用。', { exact: true }).waitFor()
  assert.ok(
    (await client.get(`${base}/canon/entities`)).some(
      (entity) => entity.name === '旧灯塔',
    ),
  )
  assert.deepEqual(errors, [])
  console.log(
    'PASS: real SQLite project, local proposal, author review, save continuity, analysis, export, concurrent conflict and reload persistence.',
  )
} catch (error) {
  reportFailure(error, backend ? [backend] : [])
  process.exitCode = 1
} finally {
  await browser?.close()
  if (vite) await stopVite(vite)
  if (backend) await stopBackend(backend)
  if (!process.exitCode) await rmTempRoot(dataRoot)
}
