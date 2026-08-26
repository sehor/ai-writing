// Shared harness for the P1-08 real-backend browser tests
// (docs/ai-writing-improvement-plan.md, section 九 / P1-08).
//
// Every helper here drives REAL infrastructure only:
//   - a real FastAPI backend (backend/.venv uvicorn) bound to a TEMP SQLite data root,
//   - a real Vite dev server serving frontend/ with an /api proxy to the temp backend,
//   - Playwright Chromium resolved from frontend/node_modules.
// There is deliberately no route mocking anywhere; the browser talks to the real app.
//
// Data-root contract: when AI_WRITING_DATA_ROOT is set, the SQLite db lives at
// <root>/app.db and the LLM Wiki / cognition file stores root at <root>/projects.
// startBackend() enforces this contract before any test step runs: if the
// backend does not materialize <root>/app.db, we abort instead of silently
// falling back to the legacy backend/data directory (which holds real data).

import { spawn } from 'node:child_process'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdtemp, readdir, rm, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

/**
 * Behavioral probe: imports the backend's own path-resolution modules with
 * AI_WRITING_DATA_ROOT set and prints where every file-backed store roots.
 * The data-root refactor lands store by store, so the harness checks all
 * three roots (SQLite via config, LLM Wiki projects root, cognition/memplace
 * modules root) and refuses to run when any of them would still write into
 * the legacy backend/data directory.
 */
const ROOT_PROBE_SNIPPET = [
  'import json',
  'from app.config import resolve_data_root',
  'from app.llm_wiki.dependencies import projects_root as wiki_root',
  'from app.cognition.registry import modules_root as cognition_root',
  'print(json.dumps({',
  '  "data_root": str(resolve_data_root()),',
  '  "wiki_root": str(wiki_root),',
  '  "cognition_root": str(cognition_root),',
  '}))',
].join('\n')

const HARNESS_DIR = resolve(import.meta.dirname ?? '.')
export const E2E_ROOT = resolve(HARNESS_DIR, '..')
export const REPO_ROOT = resolve(E2E_ROOT, '..')
export const FRONTEND_DIR = join(REPO_ROOT, 'frontend')
export const BACKEND_DIR = join(REPO_ROOT, 'backend')
// Python used to spawn uvicorn. Resolution order:
//   1. AI_WRITING_E2E_PYTHON env override (CI points this at the setup-python
//      interpreter where requirements are already installed)
//   2. the local venv (Windows layout, then POSIX layout)
//   3. whatever `python` / `python3` is on PATH
function resolveBackendPython() {
  const override = process.env.AI_WRITING_E2E_PYTHON?.trim()
  if (override) return override
  const windowsVenv = join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')
  if (existsSync(windowsVenv)) return windowsVenv
  const posixVenv = join(BACKEND_DIR, '.venv', 'bin', 'python')
  if (existsSync(posixVenv)) return posixVenv
  return process.platform === 'win32' ? 'python' : 'python3'
}
export const BACKEND_PYTHON = resolveBackendPython()

/** Fixed uncommon ports so parallel runs never collide with dev servers. */
export const PORTS = {
  fullReviewBackend: 8131,
  fullReviewVite: 5175,
  wikiFailureBackend: 8132,
  wikiFailureVite: 5176,
}

/**
 * Bounded FIFO buffer for child-process output so failure reports can include
 * a readable tail of backend logs without holding the whole stream in memory.
 */
class OutputRing {
  constructor(maxLines = 400) {
    this.maxLines = maxLines
    this.lines = []
  }

  push(chunk) {
    for (const line of chunk.toString().split(/\r?\n/)) {
      if (line.length === 0) continue
      this.lines.push(line)
    }
    if (this.lines.length > this.maxLines) {
      this.lines.splice(0, this.lines.length - this.maxLines)
    }
  }

  tail(lineCount = 40) {
    return this.lines.slice(-lineCount).join('\n')
  }
}

/** Create a fresh temporary directory used as AI_WRITING_DATA_ROOT. */
export async function mkTempRoot(prefix = 'ai-writing-e2e-') {
  return mkdtemp(join(tmpdir(), prefix))
}

/** Best-effort recursive cleanup of a temp root (Windows EBUSY tolerant). */
export async function rmTempRoot(tempRoot) {
  if (!tempRoot || !tempRoot.startsWith(tmpdir())) return
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await rm(tempRoot, { recursive: true, force: true })
      return
    } catch (error) {
      if (attempt === 2) {
        console.warn('[harness] could not fully remove ' + tempRoot + ': ' + error.message)
        return
      }
      await sleep(500)
    }
  }
}

export function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms))
}

/** Poll fn() until it returns a truthy value or the timeout elapses. */
export async function pollUntil(fn, { timeoutMs = 30000, intervalMs = 500, label = 'condition' } = {}) {
  const deadline = Date.now() + timeoutMs
  let lastError = null
  let lastValue = null
  while (Date.now() < deadline) {
    try {
      lastValue = await fn()
      if (lastValue) return lastValue
    } catch (error) {
      lastError = error
    }
    await sleep(intervalMs)
  }
  const detail = lastError
    ? '; last error: ' + lastError.message
    : '; last value: ' + JSON.stringify(lastValue)
  throw new Error('Timed out after ' + timeoutMs + 'ms waiting for ' + label + detail)
}

/** Wait until GET url answers 2xx. Returns the first ok Response. */
export async function waitForServer(url, { timeoutMs = 30000, label } = {}) {
  return pollUntil(
    async () => {
      const response = await fetch(url)
      if (response.ok) return response
      throw new Error('HTTP ' + response.status)
    },
    { timeoutMs, label: label ?? ('GET ' + url + ' answering 2xx') },
  )
}

async function killProcessTree(child, { label = 'child process' } = {}) {
  if (!child || child.exitCode !== null) return
  await new Promise((resolveKill) => {
    let settled = false
    const settle = () => {
      if (!settled) {
        settled = true
        clearTimeout(timer)
        resolveKill()
      }
    }
    const timer = setTimeout(settle, 3000)
    child.once('exit', settle)
    // Windows has no POSIX tree signals; taskkill /T takes the whole tree down.
    if (process.platform === 'win32') {
      try {
        spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
          .once('exit', settle)
      } catch {
        child.kill()
      }
    } else {
      child.kill('SIGTERM')
    }
    setTimeout(() => {
      try {
        child.kill('SIGKILL')
      } catch {
        /* already gone */
      }
    }, 2500).unref()
    void label
  })
}

/**
 * Start the real FastAPI backend bound to a temp data root.
 *
 * - cwd=backend, spawns [venvPython, -m, uvicorn, app.main:app, --host, 127.0.0.1, --port, N]
 * - sets AI_WRITING_DATA_ROOT=<dataRoot> (db at <root>/app.db, wiki roots at <root>/projects)
 * - waits for GET /api/health (default 30s)
 * - then verifies the data-root contract actually held by requiring
 *   <dataRoot>/app.db to exist; aborts with actionable diagnostics otherwise so
 *   tests can never fall back onto the developer's legacy backend/data directory.
 */
/**
 * Probe where every backend file store would root under AI_WRITING_DATA_ROOT
 * and throw unless all of them stay inside the temp data root. Keeps
 * mid-refactor trees from silently polluting the developer's legacy
 * backend/data directory.
 */
async function assertBackendFileRootsCovered(dataRoot) {
  const proc = spawn(BACKEND_PYTHON, ['-c', ROOT_PROBE_SNIPPET], {
    cwd: BACKEND_DIR,
    env: { ...process.env, AI_WRITING_DATA_ROOT: dataRoot, PYTHONUTF8: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stdout = ''
  let stderr = ''
  proc.stdout.on('data', (chunk) => { stdout += chunk.toString() })
  proc.stderr.on('data', (chunk) => { stderr += chunk.toString() })
  const exitCode = await new Promise((resolveExit) => proc.once('exit', resolveExit))
  if (exitCode !== 0) {
    throw new Error(
      'Could not probe backend data-root resolution (python -c exited ' +
        exitCode + '). stderr: ' + stderr.slice(-800),
    )
  }
  let roots
  try {
    roots = JSON.parse(stdout.trim().split(/\r?\n/).pop())
  } catch (error) {
    throw new Error('Unparsable root probe output: ' + stdout.slice(0, 400))
  }
  const expected = String(dataRoot).toLowerCase()
  const offenders = Object.entries(roots)
    .filter(([name, path]) => !String(path).toLowerCase().startsWith(expected))
    .map(([name, path]) => name + ' -> ' + path)
  if (offenders.length > 0) {
    const failure = new Error(
      [
        'AI_WRITING_DATA_ROOT=' + dataRoot + ' is only partially honored by this build.',
        'These file stores would still target the legacy backend/data directory:',
        offenders.map((line) => '  - ' + line).join('\n'),
        'The data-root refactor must land completely (see backend/app/cognition/',
        'registry.py modules_root) before the E2E suites can run.',
      ].join('\n'),
    )
    failure.dataRootNotHonored = true
    throw failure
  }
  return roots
}

export async function startBackend({ dataRoot, port, timeoutMs = 30000 }) {
  assert.ok(dataRoot && port, 'startBackend requires { dataRoot, port }')
  const stdoutRing = new OutputRing()
  const stderrRing = new OutputRing()

  const proc = spawn(
    BACKEND_PYTHON,
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, AI_WRITING_DATA_ROOT: dataRoot, PYTHONUTF8: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  proc.stdout.on('data', (chunk) => stdoutRing.push(chunk))
  proc.stderr.on('data', (chunk) => stderrRing.push(chunk))
  proc.once('exit', (code, signal) => {
    stderrRing.push('[harness] backend exited code=' + code + ' signal=' + signal)
  })

  const handle = {
    proc,
    port,
    dataRoot,
    baseUrl: 'http://127.0.0.1:' + port,
    diagnostics: () =>
      '--- backend stdout tail ---\n' + stdoutRing.tail(30) +
      '\n--- backend stderr tail ---\n' + stderrRing.tail(60),
  }

  try {
    await waitForServer(handle.baseUrl + '/api/health', {
      timeoutMs,
      label: 'backend /api/health on port ' + port,
    })

    // Contract gate: the db must live inside OUR temp root before any mutation.
    const dbPath = join(dataRoot, 'app.db')
    try {
      await pollUntil(() => existsSync(dbPath), {
        timeoutMs: 20000,
        intervalMs: 250,
        label: 'AI_WRITING_DATA_ROOT contract (' + dbPath + ' created at boot)',
      })
    } catch (gateError) {
      const message = [
        'Backend answered /api/health but did not honor AI_WRITING_DATA_ROOT=' + dataRoot,
        '(no app.db appeared inside the temp root). The current working tree still',
        'boots with the legacy backend/data paths - the data-root refactor has not',
        'landed here. Refusing to run destructive E2E flows against the real',
        'backend/data directory.',
        '',
        gateError.message,
        handle.diagnostics(),
      ].join('\n')
      const failure = new Error(message)
      failure.dataRootNotHonored = true
      throw failure
    }

    // Store-by-store gate: config/SQLite + LLM Wiki + cognition roots.
    const roots = await assertBackendFileRootsCovered(dataRoot)
    handle.resolvedRoots = roots
  } catch (error) {
    await killProcessTree(proc, { label: 'backend' })
    throw error
  }

  return handle
}

/** Stop a backend started by startBackend(). */
export async function stopBackend(handle) {
  if (!handle) return
  await killProcessTree(handle.proc, { label: 'backend' })
}

/**
 * Start a real Vite dev server for frontend/ via Vite's JS API.
 *
 * We cannot edit frontend/vite.config.ts (its proxy target is hard-coded to
 * :8000), and this suite must not touch existing files, so the harness builds
 * the same dev server programmatically: root=frontend, @vitejs/plugin-vue
 * loaded through createRequire(frontend/package.json), strictPort, and an /api
 * proxy pointed at our temp backend port. This is the identical Vite pipeline
 * the CLI would run (validated against vite 6.4.x).
 */
export async function startVite({ port, backendPort }) {
  assert.ok(port && backendPort, 'startVite requires { port, backendPort }')
  const viteEntry = join(FRONTEND_DIR, 'node_modules', 'vite', 'dist', 'node', 'index.js')
  if (!existsSync(viteEntry)) {
    throw new Error("Vite not found at " + viteEntry + ". Run 'pnpm install' inside frontend/ first.")
  }
  const vite = await import(pathToFileURL(viteEntry).href)
  const frontendRequire = createRequire(join(FRONTEND_DIR, 'package.json'))
  const vuePluginModule = frontendRequire('@vitejs/plugin-vue')
  const vuePlugin = vuePluginModule.default ?? vuePluginModule

  const server = await vite.createServer({
    configFile: false,
    root: FRONTEND_DIR,
    server: {
      host: '127.0.0.1',
      port,
      strictPort: true,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:' + backendPort,
          changeOrigin: true,
        },
      },
    },
    plugins: [vuePlugin()],
  })
  await server.listen()

  const url = 'http://127.0.0.1:' + port
  await waitForServer(url, { timeoutMs: 45000, label: 'vite dev server at ' + url })
  return { server, url, port }
}

/** Stop a Vite server started by startVite(). */
export async function stopVite(handle) {
  if (!handle) return
  try {
    await Promise.race([
      handle.server.close(),
      sleep(8000).then(() => {
        console.warn('[harness] vite close timed out after 8s; continuing teardown')
      }),
    ])
  } catch (error) {
    console.warn('[harness] vite close errored: ' + error.message)
  }
}

/** Launch Playwright Chromium using the copy installed under frontend/node_modules. */
export async function launchBrowser() {
  const frontendRequire = createRequire(join(FRONTEND_DIR, 'package.json'))
  const playwright = frontendRequire('playwright')
  return playwright.chromium.launch()
}

/**
 * Small fetch helper aimed directly at the temp backend (bypasses the browser).
 * Every method resolves to parsed JSON and throws with status + body on !ok.
 */
export function api(port) {
  const base = 'http://127.0.0.1:' + port + '/api'
  async function request(method, path, body) {
    const response = await fetch(base + path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const text = await response.text()
    if (!response.ok) {
      throw new Error(
        'API ' + method + ' ' + path + ' failed: HTTP ' + response.status + ' ' + text.slice(0, 600),
      )
    }
    return text.length ? JSON.parse(text) : null
  }
  return {
    base,
    get: (path) => request('GET', path),
    post: (path, body = {}) => request('POST', path, body),
    put: (path, body = {}) => request('PUT', path, body),
    delete: (path) => request('DELETE', path),
  }
}

/**
 * Create the blocking entry that makes every LLM Wiki write fail: a regular
 * FILE named exactly 'projects' at the data root. Wiki ingestion then tries
 * to mkdir/write below <root>/projects/<project>/... and hits ENOTDIR; the
 * memplace prose-sample writer (writeback_analysis job) fails the same way.
 */
export async function blockWikiRootWithFile(dataRoot) {
  await writeFile(join(dataRoot, 'projects'), 'e2e: blocking file so wiki writes fail\n', 'utf8')
}

/** List top-level entries of the data root (diagnostics + assertions). */
export async function listRootEntries(dataRoot) {
  try {
    return readdir(dataRoot)
  } catch (error) {
    return ['<unreadable: ' + error.message + '>']
  }
}

/**
 * Standard failure banner: prints the assertion/error plus the backend log
 * tails so a red test explains itself.
 */
export function reportFailure(error, handles = []) {
  const lines = [
    '',
    '='.repeat(78),
    'E2E FAILED: ' + (error && error.message ? error.message : String(error)),
    '='.repeat(78),
  ]
  if (error && error.stack) {
    lines.push(error.stack.split('\n').slice(1, 6).join('\n'))
  }
  for (const handle of handles) {
    if (handle && typeof handle.diagnostics === 'function') {
      lines.push(handle.diagnostics())
    }
  }
  console.error(lines.join('\n'))
}
