// AUD-22: isolated synthetic benchmark, not a paid-model or production-load test.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createServer } from 'node:net'
import { mkdir, writeFile } from 'node:fs/promises'
import { cpus, totalmem, platform, release } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { api, BACKEND_DIR, BACKEND_PYTHON, REPO_ROOT, launchBrowser, mkTempRoot, reportFailure, rmTempRoot, startBackend, startVite, stopBackend, stopVite } from './lib/harness.mjs'

const sizeIndex = process.argv.indexOf('--size')
const size = sizeIndex >= 0 ? process.argv[sizeIndex + 1] : 'small'
const tiers = size === 'all' ? ['small', 'medium', 'large'] : [size]
assert.ok(tiers.every(tier => ['small', 'medium', 'large'].includes(tier)), 'Use --size small|medium|large|all')
const repeats = 5
const summary = values => {
  const ordered = [...values].sort((a, b) => a - b)
  return { n: values.length, median: +ordered[Math.floor(ordered.length / 2)].toFixed(3), p95_nearest_rank: +ordered[Math.ceil(.95 * ordered.length) - 1].toFixed(3), max: +ordered.at(-1).toFixed(3) }
}
async function freePort() {
  const server = createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}
for (const tier of tiers) {
  const dataRoot = await mkTempRoot(`ai-writing-benchmark-${tier}-`)
  let backend, vite, browser
  const progress = { tier, pid: process.pid, data_root: dataRoot }
  async function checkpoint(stage, fields = {}) {
    Object.assign(progress, fields, { stage, at: new Date().toISOString() })
    await mkdir(join(REPO_ROOT, '.tmp'), { recursive: true })
    await writeFile(join(REPO_ROOT, '.tmp', `performance-${tier}-progress.json`), JSON.stringify(progress, null, 2))
  }
  try {
    await checkpoint('seed_and_backend_measurements')
    const seeded = JSON.parse(execFileSync(BACKEND_PYTHON, ['-m', 'scripts.benchmark_longform', '--size', tier, '--root', dataRoot, '--repeats', String(repeats)], {
      cwd: BACKEND_DIR, env: { ...process.env, PYTHONIOENCODING: 'utf-8', AI_WRITING_DATA_ROOT: dataRoot }, encoding: 'utf8', timeout: 240000, maxBuffer: 4 * 1024 * 1024,
    }).trim().split('\n').at(-1))
    const fixture = seeded.fixture
    await checkpoint('backend_complete', { backend: seeded.backend })
    const backendPort = await freePort()
    backend = await startBackend({ port: backendPort, dataRoot })
    const client = api(backendPort)
    const base = `/projects/${fixture.project_id}`
    const http = {}
    for (const [name, path, expected] of [
      ['scenes', `${base}/scene-contracts`, fixture.scene_count],
      ['history', `${base}/manuscript/revisions`, fixture.revision_count],
      ['prose', `${base}/manuscript/scenes`, fixture.scene_count],
      ['export', `${base}/manuscript/export`, null],
      ['backup', `${base}/backup`, null],
    ]) {
      await checkpoint(`http_${name}`)
      const times = [], parse = []
      let bytes = 0
      for (let i = 0; i < repeats; i++) {
        const start = performance.now()
        const response = await fetch(`http://127.0.0.1:${backendPort}/api${path}`)
        assert.ok(response.ok, `${name} HTTP ${response.status}`)
        const body = await response.arrayBuffer()
        times.push(performance.now() - start)
        bytes = body.byteLength
        if (name !== 'backup') {
          const parseStart = performance.now()
          const result = JSON.parse(new TextDecoder().decode(body))
          parse.push(performance.now() - parseStart)
          if (expected !== null) assert.equal(result.length, expected, `${name} must not silently truncate`)
          if (name === 'prose') assert.equal(result.reduce((n, scene) => n + scene.content.length, 0), fixture.accepted_prose_chars)
          if (name === 'export') assert.equal(result.scene_count, fixture.scene_count)
        }
      }
      http[name] = { response_ms: summary(times), bytes, ...(parse.length ? { node_json_parse_ms: summary(parse) } : {}) }
    }
    await checkpoint('http_complete', { http })
    const invalid = await fetch(`http://127.0.0.1:${backendPort}/api${base}/scene-contracts`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sequence: 1000, title: 'Must reject' }),
    })
    assert.equal(invalid.status, 422)
    const oversized = await fetch(`http://127.0.0.1:${backendPort}/api${base}/manuscript/scenes/${fixture.scene_ids[0]}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: 'Must reject', content: '文'.repeat(40001), expected_scene_version: 3 }),
    })
    assert.equal(oversized.status, 422)
    assert.equal((await client.get(`${base}/manuscript/revisions`)).length, fixture.revision_count)

    vite = await startVite({ port: await freePort(), backendPort })
    browser = await launchBrowser()
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    page.setDefaultTimeout(60000)
    page.on('dialog', dialog => dialog.accept())
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const cdp = await page.context().newCDPSession(page)
    await cdp.send('Performance.enable')
    const metrics = async () => Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(m => [m.name, m.value]))
    const observations = {}
    async function observe(name, action) {
      await checkpoint(`browser_${name}_${observations[name]?.length ?? 0}`, { browser_observations: observations })
      const before = await metrics(), start = performance.now()
      await action()
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      const elapsed = performance.now() - start, after = await metrics()
      ;(observations[name] ??= []).push({ elapsed_ms: elapsed,
        script_ms: Math.max(0, (after.ScriptDuration - before.ScriptDuration) * 1000),
        layout_ms: Math.max(0, (after.LayoutDuration - before.LayoutDuration) * 1000),
        task_ms: Math.max(0, (after.TaskDuration - before.TaskDuration) * 1000),
        js_heap_mib: after.JSHeapUsedSize / 1048576,
      })
    }
    async function pick(title) {
      await page.locator('.project-dialog-trigger').click()
      await page.locator('.project-picker-list button', { hasText: title }).click()
      await page.locator('.project-dialog').waitFor({ state: 'hidden' })
      await page.locator('.workspace-content[aria-busy="false"]').waitFor()
    }
    await observe('boot_dev_server', async () => {
      await page.goto(vite.url)
      await page.waitForLoadState('networkidle')
      await page.locator('.workspace-content[aria-busy="false"]').waitFor()
    })
    const editor = page.getByRole('textbox', { name: '正文内容', exact: true })
    await observe('first_project_open', async () => {
      await pick(fixture.project_title)
      await page.getByRole('button', { name: '正文写作', exact: true }).click()
      await editor.waitFor()
    })
    assert.equal(await page.locator('.scene-link').count(), fixture.scene_count)
    for (let i = 0; i < repeats; i++) {
      await observe('project_switch_roundtrip', async () => {
        await pick(fixture.other_project_title)
        await pick(fixture.project_title)
        await page.getByRole('button', { name: '正文写作', exact: true }).click()
        await editor.waitFor()
      })
      await observe('scene_switch', async () => {
        const title = i % 2 ? 'Scene 0001' : `Scene ${String(fixture.scene_count).padStart(4, '0')}`
        await page.locator('.scene-link', { hasText: title }).click()
        await page.waitForFunction(expected => document.querySelector('[aria-label="正文内容"]')?.value.includes(`合成场景${expected}。`), i % 2 ? '0001' : String(fixture.scene_count).padStart(4, '0'))
      })
      await observe('history_panel_open', async () => {
        await page.getByRole('button', { name: '版本历史', exact: true }).click()
        await page.locator('.revision-history').waitFor()
      })
      await page.getByRole('button', { name: '关闭辅助面板', exact: true }).click()
    }
    await page.screenshot({ path: join(REPO_ROOT, '.tmp', `performance-${tier}.png`) })
    const apiResources = await page.evaluate(() => performance.getEntriesByType('resource').filter(entry => entry.name.includes('/api/')).map(entry => ({ duration: entry.duration, path: new URL(entry.name).pathname })))
    const browserMeasurements = Object.fromEntries(Object.entries(observations).map(([name, rows]) => [name, Object.fromEntries(Object.keys(rows[0]).map(key => [key, summary(rows.map(row => row[key]))]))]))
    assert.deepEqual(errors, [])
    // A loose representative smoke budget catches hangs, not machine-to-machine jitter.
    if (tier === 'small') assert.ok(browserMeasurements.project_switch_roundtrip.elapsed_ms.max < 15000, 'Small project switch exceeded 15 s safety budget')
    const { scene_ids, ...counts } = fixture
    const report = { ...seeded, protocol_version: 2, fixture: { ...counts, first_scene: scene_ids[0], last_scene: scene_ids.at(-1) }, http, browser: browserMeasurements,
      browser_version: browser.version(), host: { os: `${platform()} ${release()}`, cpu: cpus()[0]?.model, logical_cpus: cpus().length, ram_gib: +(totalmem() / 1073741824).toFixed(2), node: process.version },
      browser_api_resources: { count: apiResources.length, slowest: apiResources.sort((a, b) => b.duration - a.duration).slice(0, 5) },
      limits_verified: { sequence_1000: 422, prose_40001: 422, scene_count_not_truncated: true, history_count_not_truncated: true },
      caveat: 'Vite dev server and isolated headless Chromium, no CPU throttling. CDP durations are main-thread costs, not elapsed-minus-network estimates. Repeated project switching is a two-project round trip. n=5 p95 is sample maximum, not a population SLA.',
    }
    await mkdir(join(REPO_ROOT, '.tmp'), { recursive: true })
    await writeFile(join(REPO_ROOT, '.tmp', `performance-${tier}.json`), JSON.stringify(report, null, 2))
    await checkpoint('completed')
    console.log(JSON.stringify(report))
    console.log(`PASS ${tier}: ${fixture.scene_count} scenes, ${fixture.revision_count} revisions; exact text/history restored, HTTP over-limit writes rejected.`)
  } catch (error) {
    await checkpoint('failed', { failed_stage: progress.stage, error: String(error) })
    reportFailure(error, [backend, vite])
    process.exitCode = 1
    break
  } finally {
    await browser?.close()
    await stopVite(vite)
    await stopBackend(backend)
    await rmTempRoot(dataRoot)
  }
}
