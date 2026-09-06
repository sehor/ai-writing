# e2e — P1-08 真实后端浏览器测试

当前中文工作台使用 `pnpm test:e2e`：运行 `workspace-review.e2e.mjs` 和 `workspace-wiki-failure.e2e.mjs`。前者覆盖真实后端的草稿审核、持续编辑、分析、导出、冲突、恢复与设定回写；后者覆盖文件存储故障和界面重试。前者使用临时端口，后者沿用下文的 8132 / 5176，所有数据均隔离。

`pnpm test:browser` 使用随机端口与本地模拟数据，检查浅深主题、桌面及窄屏交互，并生成 `.tmp/ui-review/` 截图。

以下是重构前完整场景的历史说明。旧版入口保留为 `pnpm test:e2e:legacy`，其页面选择器对应旧界面，不作为当前工作台的验收命令。

Real-browser E2E suite from the archived `docs/older/ai-writing-improvement-plan.md`, section 九 / P1-08:
a **real FastAPI backend** over a **temp SQLite data root**, a **real Vite dev server**,
**Playwright Chromium**, and the **local deterministic provider** (no API keys, no
DEEPSEEK_* env needed). Nothing is route-mocked — every `/api` call the page makes
reaches the spawned backend through the Vite proxy.

## Files

| File | Purpose |
| --- | --- |
| `lib/harness.mjs` | Shared helpers: temp roots, backend/Vite lifecycle, health waits, API client |
| `full-review-loop.e2e.mjs | Happy path: project → Step 7 → Canon proposals → chapter/scene → proposal accept → auto-analysis → write-back accept → export → restart persistence → Step 8 parse + batch accept → scene edit v2 → restore v1 |
| `wiki-failure.e2e.mjs` | Failure path: blocked LLM Wiki root, core data survives, UI shows failed job, UI Retry repairs it, no duplicate versions |

## Prerequisites

- Backend venv present: `backend\.venv\Scripts\python.exe` (fastapi + uvicorn installed).
- Frontend deps installed (`frontend/node_modules` provides vite, @vitejs/plugin-vue and playwright).
- Playwright Chromium browser binaries. If missing, run once:

      cd frontend
      pnpm exec playwright install chromium

## How to run

Run each script from inside `e2e/`:

    cd e2e
    node full-review-loop.e2e.mjs
    node wiki-failure.e2e.mjs

No NODE_PATH tricks are required: the harness resolves `vite` and `playwright`
through `createRequire(frontend/package.json)`, so the exact copies installed under
`frontend/node_modules` are used regardless of cwd. Each script exits 0 on success,
1 on any assertion failure, and always kills its child processes and removes its
temp data root (kept only on failure paths where diagnostics reference it).

## Ports

Fixed uncommon ports so the tests never collide with a dev server you may have running:

| Script | Backend (uvicorn) | Vite dev server |
| --- | --- | --- |
| `full-review-loop.e2e.mjs` | 8131 | 5175 |
| `wiki-failure.e2e.mjs` | 8132 | 5176 |

Vite runs with `strictPort`; make sure those ports are free. The frontend's own
`vite.config.ts` proxies `/api` to hard-coded port 8000, which this suite must not
modify — so the harness starts Vite through its JavaScript API with the same root,
plugin, and pipeline, but an `/api` proxy pointed at the chosen temp backend port.

## The AI_WRITING_DATA_ROOT contract gate

Each script spawns uvicorn with `AI_WRITING_DATA_ROOT=<mkdtemp under os.tmpdir()>`.
Per contract, the SQLite db then lives at `<root>/app.db` and every file-backed
store roots at `<root>/projects`. `startBackend()` applies two gates before any
test step runs:

1. Waits for `GET /api/health` (30s timeout, stdout/stderr ring buffers kept for
   diagnostics), then **requires `<root>/app.db` to exist**.
2. Runs a behavioral probe (`python -c` importing the backend's own modules with
   the env var set) and requires **all three** file stores to resolve inside the
   temp root: `config.resolve_data_root`, `llm_wiki.dependencies.projects_root`,
   and `cognition.registry.modules_root`.

If any gate fails (data-root refactor incomplete), the suite aborts with an
actionable message naming the offending store instead of silently falling back to
— and polluting — the legacy `backend/data` directory. Both scripts additionally
verify wiki files land under `<root>/projects/<project id>` after successful
ingestion.

## What the happy path asserts (full-review-loop.e2e.mjs)

UI flow with the real labels/selectors used:

1. **Create project** — opens the project dialog, expands `Create new project`,
   fills the title/premise, and asserts `.topbar h2` shows the title.
2. **Save Step 7** — sidebar step selector aria-label `Open step 7: Character Bible`,
   `.artifact-editor textarea`, button `Save Artifact`, status text `Artifact saved.`
3. **Compile Canon proposals** — heading `Step 7: Compile into Canon Proposals`,
   button `Extract Canon Proposals`, summary line asserting `1 proposal(s): 1 create, 0 update.`
4. **Accept Canon proposal** — Manuscript nav → Write-backs panel
   (`.writeback-review .proposal-list`) item `Create canon character: Mira` →
   detail `Accept` → status `Write-back accepted and applied.`; Canon nav →
   `.canon-list` shows Mira; API: entity version 1.
5. **Chapter + Scene contract** — `New Chapter` / `.chapter-editor` inputs →
   `Create Chapter` → `.chapter-list` item `Chapter 1: The Locked Map`;
   `New Scene` / `.scene-editor` (chapter select, sequence, title `Archive Threshold`,
   POV `Mira`, Goal / Conflict / Turning Point / Required Canon / Forbidden Facts /
   Open Threads textareas) → `Create Scene`; API asserts all contract fields persisted.
6. **Create Proposal → Accept** — buttons `Create Proposal` and `Accept`;
   asserts the accepted-scene indicator `Chapter 1: The Locked Map / Version 1`.
7. **Post-Acceptance Analysis** — polls the same API the UI uses
   (`GET .../outbox-jobs`) until `llm_wiki_ingest`, `consistency_analysis`, and
   `writeback_analysis` all report `succeeded`, then asserts all three chips
   render `succeeded` in the `.post-accept-analysis` panel; Revision History shows
   `Version 1`; the `.consistency-report` section loads without an error banner.
8. **Write-back acceptance** — asserts the deterministic provider auto-created a
   memory-record proposal (`Prose sample from 1. Archive Threshold`). Because no
   `action=update` proposal is generated automatically (see deviations), the test
   seeds one over REST, clicks the panel `Refresh`, selects
   `Update canon character: Mira`, accepts it in the browser, and asserts over the
   API that Mira's `version` bumped to 2 with the new `current_state` applied.
9. **Export Markdown** — button `Export Markdown`; output contains
   `# Mira Archive`, `## Chapter 1: The Locked Map`, `### 1. Archive Threshold`.
10. **Restart persistence** — the backend process is stopped and restarted against
    the SAME temp root on the same port; the page is reloaded, the project is
    re-selected from the `Open project` dialog; Canon still shows Mira (with the
    updated state in the editor), Manuscript still shows chapter, scene, and the
    Version 1 scene/revision; APIs confirm exactly one revision/scene at version 1.
11. **Step 8 compiler** — sidebar step selector `Open step 8: Scene List`, save the
    two-scene artifact (`Artifact saved.`), heading `Step 8: Parse into Scene
    Proposals`, button `Parse Scene Proposals`, status `Parsed 2 scene proposal(s).`,
    both rows render in `.scene-proposal-table`; `Accept All Pending` reports
    `Created 2 scene contract(s) from parsed proposals.`; over the API both
    contracts exist at sequences 2/3 with the chapter hint resolved to Chapter 1,
    required canon resolved, and both proposals moved to `accepted`; the new
    contracts appear in the Manuscript `.scene-list`.
12. **Direct scene edit** — `Edit` on the accepted `Archive Threshold` item,
    replace the content, `Save Version`; the accepted item flips to `Version 2`,
    the API shows scene version 2 with the edited prose and exactly revisions
    v1+v2, Revision History lists `Version 2`.
13. **Revision restore** — `Restore` on the `Version 1` history item; the scene
    becomes `Version 3` carrying the ORIGINAL v1 content again (asserted in UI
    and API), all three revisions remain (versions 1..3), and the v3 revision
    row stores the restored prose.

## What the failure path asserts (wiki-failure.e2e.mjs)

Before boot, a plain FILE named exactly `projects` is created inside the temp root.
Both file-backed stores root there, so accepting a manuscript proposal fails
`llm_wiki_ingest` and `writeback_analysis` (memplace prose samples) while the
DB-only `consistency_analysis` succeeds. Assertions:

- Core data persists: `Chapter 1: Fault Lines / Version 1` visible; exactly one
  revision and one manuscript scene at version 1 over the API.
- Outbox truth: `llm_wiki_ingest` failed with an error message,
  `writeback_analysis` failed, `consistency_analysis` succeeded.
- The Manuscript workspace Post-Acceptance Analysis panel renders the failed
  `Write-back suggestions` and `Wiki index` job chips (`failed`), their error text,
  and a `Retry` button each; the consistency chip reads `succeeded`.
- After deleting the blocking file and clicking the panel's `Retry` on both failed
  jobs, the chips flip to `succeeded`, the API agrees, the prose sample file appears
  under `<root>/projects/<project>/modules/memplace/prose_samples/`, and the retried
  ingest stages wiki sources under `modules/llm_wiki/sources/` proving the recovered
  wiki write path.
- No duplicate versions: still exactly one revision / one scene, both version 1,
  and single entries rendered in Accepted Manuscript and Revision History panels.

## Documented deviations

- **Seeded write-back proposal.** The deterministic provider's post-acceptance
  analysis generates only a memory-record create proposal ("Prose sample"), never an
  `action=update` proposal against Canon. To exercise browser acceptance of a Canon
  update (the plan's "接受 Write-back Update → 验证 Canon 已更新"), the happy-path
  test seeds a valid `canon_entity`/`update` proposal via
  `POST /api/projects/{id}/writeback/proposals` (with matching `expected_version`)
  and then accepts it exclusively through the Write-backs UI.
- **Vite via JS API instead of CLI spawn.** Equivalent dev server (same root/plugin/
  strictPort behavior), chosen so the `/api` proxy can target the per-test backend
  port without editing `frontend/vite.config.ts`.

## Known limitations

- ~~Canon editor draft does not populate when selecting a list entry~~ — fixed:
  the selection watcher now applies the entity baseline before restoring any cached
  draft (`frontend/src/stores/canon.ts`).
- ~~`llm_wiki_ingest` job failures have no dedicated UI surface~~ — fixed: the
  Post-Acceptance Analysis panel now lists all three job types and offers the same
  Retry action for the wiki index job; the failure-path test clicks it in the UI.
- The Canon workspace caches the selected entity's form draft until remount, so the
  happy path checks the updated `current_state` in the editor after the reload of the
  restart-persistence phase, plus immediately over the API right after acceptance.
- Cross-platform: uvicorn is spawned through `BACKEND_PYTHON`, resolved as
  `AI_WRITING_E2E_PYTHON` → local venv (Windows or POSIX layout) → PATH python;
  process-tree cleanup uses `taskkill /T` on Windows and signals elsewhere.
- Scripts are plain Node (>=18) ESM with no package.json of their own, per the
  constraint of not touching existing repo files.
