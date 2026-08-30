import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
import { chromium } from 'playwright'

const frontendUrl = 'http://127.0.0.1:5174'
const frontendDir = fileURLToPath(new URL('..', import.meta.url))
const viteBin = join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js')

const state = {
  project: {
    id: 'demo-novel',
    title: 'Demo Novel',
    premise: 'A cartographer maps a city that resists memory.',
    current_step: 1,
  },
  chapters: [],
  scenes: [],
  proposals: [],
  manuscriptScenes: [],
  revisions: [],
  writebacks: [],
  references: [],
  graphAvailable: false,
  graphRequestCount: 0,
}

function nextId(prefix, items) {
  return `${prefix}-${items.length + 1}`
}

function jsonResponse(payload, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  }
}

async function handleApi(route) {
  const request = route.request()
  const url = new URL(request.url())
  const path = url.pathname.replace(/^\/api/, '')
  const method = request.method()
  const body = request.postData() ? JSON.parse(request.postData()) : {}

  if (method === 'GET' && path === '/health') {
    return route.fulfill(jsonResponse({ status: 'ok', service: 'ai-writing-backend' }))
  }
  if (method === 'GET' && path === '/projects') {
    return route.fulfill(jsonResponse([state.project]))
  }
  if (method === 'GET' && path === '/snowflake/steps') {
    return route.fulfill(jsonResponse([{ number: 1, title: 'One Sentence', artifact: 'story_contract', description: 'Story promise.' }]))
  }
  if (method === 'GET' && path === '/snowflake/workflow/status') {
    return route.fulfill(jsonResponse({ runtime: 'local_deterministic', provider: 'local', provider_configured: false, model: '', base_url: '', details: 'Local browser test runtime.' }))
  }

  if (method === 'GET' && path.endsWith('/snowflake/artifacts')) return route.fulfill(jsonResponse([]))
  if (method === 'GET' && path.endsWith('/canon/entities')) return route.fulfill(jsonResponse([]))
  if (method === 'GET' && path.endsWith('/memory/records')) return route.fulfill(jsonResponse([]))
  if (method === 'GET' && path.endsWith('/manuscript/chapters')) return route.fulfill(jsonResponse(state.chapters))
  if (method === 'GET' && path.endsWith('/scene-contracts')) return route.fulfill(jsonResponse(state.scenes))
  if (method === 'GET' && path.endsWith('/manuscript/proposals')) return route.fulfill(jsonResponse(state.proposals))
  if (method === 'GET' && path.endsWith('/manuscript/scenes')) return route.fulfill(jsonResponse(state.manuscriptScenes))
  if (method === 'GET' && path.endsWith('/manuscript/revisions')) return route.fulfill(jsonResponse(state.revisions))
  if (method === 'GET' && path.endsWith('/writeback/proposals')) return route.fulfill(jsonResponse(state.writebacks))
  if (method === 'GET' && path.endsWith('/references/suggestions')) return route.fulfill(jsonResponse(state.references))
  if (method === 'GET' && path.endsWith('/outbox-jobs')) return route.fulfill(jsonResponse([]))
  if (method === 'GET' && path.includes('/analysis/consistency/from-revision/')) {
    return route.fulfill(jsonResponse({ detail: 'analysis not ready' }, 404))
  }
  if (method === 'GET' && path.endsWith('/graph/analysis')) {
    state.graphRequestCount += 1
    if (!state.graphAvailable) {
      return route.fulfill(jsonResponse({ detail: 'advisory graph unavailable' }, 503))
    }
    return route.fulfill(jsonResponse({
      project_id: state.project.id,
      summary: { node_count: 0, edge_count: 0, risk_count: 0, critical_count: 0, warning_count: 0, unresolved_thread_count: 0, canon_reference_count: 0 },
      nodes: [],
      edges: [],
      risks: [],
    }))
  }

  if (method === 'POST' && path.endsWith('/manuscript/chapters')) {
    const chapter = { id: nextId('chapter', state.chapters), project_id: state.project.id, ...body }
    state.chapters.push(chapter)
    return route.fulfill(jsonResponse(chapter, 201))
  }
  if (method === 'POST' && path.endsWith('/scene-contracts')) {
    const scene = { id: nextId('scene', state.scenes), project_id: state.project.id, ...body }
    state.scenes.push(scene)
    return route.fulfill(jsonResponse(scene, 201))
  }
  if (method === 'POST' && /\/manuscript\/proposals\/from-scene\/[^/]+$/.test(path)) {
    const sceneId = path.split('/').at(-1)
    const scene = state.scenes.find((item) => item.id === sceneId)
    const proposal = {
      id: nextId('proposal', state.proposals),
      project_id: state.project.id,
      scene_id: sceneId,
      source: 'scene_contract',
      title: `${scene.sequence}. ${scene.title}`,
      content: `# ${scene.title}\n\nMira tests the archive door.`,
      context: 'Browser smoke context',
      checklist: ['reviewed in browser test'],
      status: 'pending_review',
      created_at: '2026-05-26T00:00:00Z',
      reviewed_at: '',
    }
    state.proposals.unshift(proposal)
    return route.fulfill(jsonResponse(proposal, 201))
  }
  if (method === 'PUT' && /\/manuscript\/proposals\/[^/]+\/status$/.test(path)) {
    const proposalId = path.split('/').at(-2)
    const proposal = state.proposals.find((item) => item.id === proposalId)
    proposal.status = body.status
    proposal.reviewed_at = '2026-05-26T00:00:01Z'
    if (body.status === 'accepted') {
      const scene = {
        id: `manuscript-${proposal.scene_id}`,
        project_id: state.project.id,
        scene_id: proposal.scene_id,
        proposal_id: proposal.id,
        title: proposal.title,
        content: proposal.content,
        version: 1,
        accepted_at: proposal.reviewed_at,
      }
      state.manuscriptScenes = [scene]
      state.revisions = [{ ...scene, id: 'revision-1', created_at: proposal.reviewed_at }]
    }
    return route.fulfill(jsonResponse(proposal))
  }
  if (method === 'GET' && path.endsWith('/manuscript/export')) {
    return route.fulfill(jsonResponse({
      project_id: state.project.id,
      title: state.project.title,
      scene_count: state.manuscriptScenes.length,
      generated_at: '2026-05-26T00:00:02Z',
      content: '# Demo Novel\n\n## Chapter 1: The Locked Map\n\n### 1. Archive Threshold\n\nMira tests the archive door.',
    }))
  }
  if (method === 'POST' && path.endsWith('/references/suggestions/generate')) {
    const suggestion = {
      id: nextId('reference', state.references),
      project_id: state.project.id,
      suggestion_type: body.suggestion_type,
      scope_type: body.scope_type,
      scope_ref: body.scope_ref,
      title: 'Scene Bridge for Archive Threshold',
      content: '# Scene Bridge\n\nLet the map fail before it helps.',
      rationale: 'Keeps the obstacle active while moving the scene forward.',
      used_context: body.author_problem,
      canon_warnings: ['Preserve the patron mystery.'],
      style_notes: [],
      graph_warnings: [],
      proposed_writebacks: [],
      workflow_trace: [],
      status: 'pending_review',
      created_at: '2026-05-26T00:00:03Z',
      reviewed_at: '',
    }
    state.references.unshift(suggestion)
    return route.fulfill(jsonResponse(suggestion, 201))
  }
  if (method === 'PUT' && /\/references\/suggestions\/[^/]+\/status$/.test(path)) {
    const suggestionId = path.split('/').at(-2)
    const suggestion = state.references.find((item) => item.id === suggestionId)
    suggestion.status = body.status
    suggestion.reviewed_at = '2026-05-26T00:00:04Z'
    return route.fulfill(jsonResponse(suggestion))
  }

  throw new Error(`Unhandled ${method} ${path}`)
}

async function waitForServer(url) {
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 250))
    }
  }
  throw new Error(`Timed out waiting for ${url}`)
}

const server = spawn(
  process.execPath,
  [viteBin, '--host', '127.0.0.1', '--port', '5174', '--strictPort'],
  { cwd: frontendDir, stdio: 'ignore' },
)

let browser
try {
  await waitForServer(frontendUrl)
  browser = await chromium.launch()
  const page = await browser.newPage()
  await page.route(`${frontendUrl}/api/**`, handleApi)
  await page.goto(frontendUrl)

  await page.getByRole('button', { name: 'Manuscript' }).click()

  await page.locator('.chapter-editor input').nth(0).fill('1')
  await page.locator('.chapter-editor input').nth(1).fill('The Locked Map')
  await page.locator('.chapter-editor textarea').fill('Mira reaches the sealed archive.')
  await page.getByRole('button', { name: 'Create Chapter' }).click()
  await page.getByRole('button', { name: /Chapter 1: The Locked Map/ }).waitFor()

  await page.getByRole('button', { name: 'New Scene' }).click()
  await page.locator('.scene-editor input').nth(0).fill('1')
  await page.locator('.scene-editor input').nth(1).fill('Archive Threshold')
  await page.locator('.scene-editor input').nth(2).fill('Mira')
  await page.locator('.scene-editor input').nth(3).fill('8')
  await page.locator('.scene-editor textarea').nth(0).fill('Enter the archive.')
  await page.locator('.scene-editor textarea').nth(1).fill('The map refuses the door.')
  await page.locator('.scene-editor textarea').nth(2).fill('The map redraws itself.')
  await page.locator('.scene-editor textarea').nth(3).fill('Mira carries the altered map.')
  await page.locator('.scene-editor textarea').nth(4).fill("The patron's identity.")
  await page.locator('.scene-editor textarea').nth(5).fill('Who changed the map?')
  await page.getByRole('button', { name: 'Create Scene' }).click()
  await page.getByRole('button', { name: /1\. Archive Threshold/ }).waitFor()

  await page.getByRole('button', { name: 'Create Proposal' }).click()
  await page.getByRole('heading', { name: '1. Archive Threshold' }).waitFor()
  await page.getByRole('button', { name: 'Accept' }).click()
  await page.getByText('Chapter 1: The Locked Map / Version 1').waitFor()

  await page.getByRole('button', { name: 'Export Markdown' }).click()
  await page.getByText('## Chapter 1: The Locked Map').waitFor()

  await page.locator('.reference-form textarea').fill('Need a bridge into the archive without revealing the patron.')
  await page.locator('.reference-form input').last().fill('One scene bridge.')
  await page.getByRole('button', { name: 'Generate Reference' }).click()
  await page.getByRole('heading', { name: 'Scene Bridge for Archive Threshold' }).waitFor()
  await page.getByRole('button', { name: 'Accept Reference' }).click()
  await page.getByText('Reference accepted.').waitFor()

  assert.equal(state.proposals[0].status, 'accepted')
  assert.equal(state.references[0].status, 'accepted')
  assert.ok(
    state.graphRequestCount > 0,
    'authoring refreshes attempted advisory graph analysis while it was unavailable',
  )

  await page.getByRole('button', { name: 'Graph' }).click()
  const graphWorkspace = page.locator('.graph-workspace')
  await graphWorkspace.getByText('Graph analysis could not be loaded.').waitFor()

  state.graphAvailable = true
  await graphWorkspace.getByRole('button', { name: 'Refresh' }).click()
  await graphWorkspace.getByText('No structural risks detected.').waitFor()
} finally {
  await browser?.close()
  if (server.exitCode === null) {
    server.kill()
    await Promise.race([
      new Promise((resolve) => server.once('exit', resolve)),
      new Promise((resolve) => setTimeout(resolve, 5000)),
    ])
  }
}
