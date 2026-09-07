import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { test } from 'node:test'

const root = new URL('../../', import.meta.url)
const read = path => readFileSync(new URL(path, root), 'utf8')

test('current author acceptance evidence links exist and each browser scenario is a real package gate', () => {
  const matrixUrl = new URL('docs/author-acceptance-matrix.md', root)
  const matrix = readFileSync(matrixUrl, 'utf8')
  const pkg = JSON.parse(read('frontend/package.json'))
  for (const scenario of ['场景 A', '场景 B', '场景 C']) assert.ok(matrix.includes(scenario))
  for (const [, target] of matrix.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
    if (/^(https?:|mailto:|#)/.test(target)) continue
    assert.ok(existsSync(new URL(target.split('#')[0], matrixUrl)), `missing acceptance evidence: ${target}`)
  }
  const scripts = ['structured-drafting', 'workspace-review', 'workspace-wiki-failure', 'scene-record-update', 'copilot-selection', 'narrative-maintenance', 'manuscript-volumes']
  for (const script of scripts) {
    const filename = `${script}.e2e.mjs`
    assert.ok(matrix.includes(filename), `matrix missing ${filename}`)
    assert.ok(pkg.scripts['test:e2e'].includes(filename), `not in current gate: ${filename}`)
  }
  assert.ok(pkg.scripts['test:perf'].includes('--size small'))
  assert.ok(!pkg.scripts['test:e2e'].includes('full-review-loop.e2e.mjs'), 'legacy English selectors are not the current gate')
})

test('frozen capacity evidence records all tiers, timing scope and integrity without implying a performance SLA', () => {
  const baseline = JSON.parse(read('docs/performance/2026-09-07-baseline.json'))
  assert.equal(baseline.protocol_version, 2)
  assert.equal(baseline.method.n, 5)
  assert.ok(baseline.method.p95.includes('not a population SLA'))
  for (const tier of ['small', 'medium', 'large']) {
    const sample = baseline[tier]
    assert.equal(sample.fixture.revisions, sample.fixture.scenes * 3)
    assert.equal(sample.fixture.current_prose_chars, sample.fixture.scenes * sample.fixture.chars_per_scene)
    assert.match(sample.restored_prose_sha256, /^[a-f0-9]{64}$/)
    for (const [median, maximum] of Object.values(sample.browser_ms)) assert.ok(median > 0 && maximum >= median)
  }
  assert.equal(baseline.verified_for_all_tiers.scene_sequence_1000_http_status, 422)
  assert.ok(baseline.unverified.includes('paid model quality'))
})
