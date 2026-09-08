# e2e — 当前中文工作台验收

更新日期：2026-09-07；完整需求映射和未验证范围见 [作者验收矩阵](../docs/author-acceptance-matrix.md)。`pnpm test:e2e` 当前串行运行以下7条真实后端浏览器用例，不使用旧英文选择器作为门禁。

| 文件 | 证据与夹具范围 |
|---|---|
| `structured-drafting.e2e.mjs` | A：真实API准备项目，UI创建章/场景→本地生成→改稿→刷新草稿→明确接受→后端重启/重开UI，正文和修订ID保持 |
| `workspace-review.e2e.mjs` | A/C：真实服务+受控Fake生成完整审核材料；UI审核、保存、并发409、导出；有来源的待审Canon候选经UI接受后才生效，新场景安全上下文读取已确认约束；重启保留 |
| `workspace-wiki-failure.e2e.mjs` | C：阻塞模块存储制造真实失败，UI显示范围/未执行CLP、重试成功、不多建正文版本 |
| `scene-record-update.e2e.mjs` | Step8回改、更新提案、目标版本冲突、重编译、稳定场景/历史与正文规划过期提示 |
| `copilot-selection.e2e.mjs` | B：两类草稿选区→建议→预览/应用/Undo；重复/过期保护；显式保存才产生v2，刷新保留且参考采纳状态不被暗改 |
| `narrative-maintenance.e2e.mjs` | 事实/知识UI维护、草稿恢复、场景预览、未来事实不进入当前Reference安全上下文 |
| `manuscript-volumes.e2e.mjs` | 卷创建、更名、排序、归卷/移出、项目隔离、草稿刷新恢复、删卷不删章/场景/正文历史 |

所有脚本通过共享harness检查临时SQLite与模块数据根，使用合成文本、独立浏览器及受控本地/Fake路径，没有真实付费模型调用或真实作者数据。大多数使用随机端口；`workspace-wiki-failure.e2e.mjs` 保留8132/5176，启动前应空闲。`finally` 关闭各自子进程，部分失败用例保留其隔离数据供排查，绝不清理作者目录。

从frontend目录运行（已安装锁定依赖和浏览器时无需重复安装）：

```powershell
rtk pnpm exec playwright install chromium
rtk pnpm test:e2e
rtk pnpm test:perf
```

CI在Linux安装Playwright系统依赖，`AI_WRITING_E2E_PYTHON` 指向 `backend/.venv/bin/python`；本地harness自动识别Windows/POSIX后端虚拟环境。工作流还配置20场景small性能门禁和JSON/截图证据保留，**当前远端Actions未执行**，不能把配置存在说成远端全绿。

性能测量不混进7条功能E2E：`pnpm test:perf` 仅small；`pnpm test:perf:full` 全三档；短时限执行器宜在根目录逐次运行 `rtk proxy node e2e/longform-benchmark.mjs --size medium` 与 `--size large`。细分耗时、机器、容量限制、一次全档工具超时和后续完整大档结果见 [性能基线](../docs/performance-baseline.md)。999场景的完整性通过不代表历史面板性能达标。

`pnpm test:browser` 使用本地模拟数据验证主题/窄屏，属于可选视觉smoke，不替代上述真实SQLite验收。专用多级Redo未实现；当前B用例验证单次安全Undo和明确重新应用/保存，不虚构Redo覆盖。

## 历史归档：原P1-08流程说明

以下内容保留重构前背景。`pnpm test:e2e:legacy` 指向旧界面，不是当前工作台验收；其中旧状态/选择器及历史限制不得直接复制成当前结论。

Real-browser E2E suite from the archived `docs/older/ai-writing-improvement-plan.md`, section 九 / P1-08:
a **real FastAPI backend** over a **temp SQLite data root**, a **real Vite dev server**,
**Playwright Chromium**, and the **local deterministic provider** (no API keys, no
DEEPSEEK_* env needed). Nothing is route-mocked — every `/api` call the page makes
reaches the spawned backend through the Vite proxy.

## Files

| File | Purpose |
| --- | --- |
| `lib/harness.mjs` | Shared helpers: temp roots, backend/Vite lifecycle, health waits, API client |
| `full-review-loop.e2e.mjs` | Happy path: project → Step 7 → Canon proposals → chapter/scene → proposal accept → auto-analysis → write-back accept → export → restart persistence → Step 8 parse + batch accept → scene edit v2 → restore v1 |
| `wiki-failure.e2e.mjs` | Failure path: blocked LLM Wiki root, core data survives, UI shows failed job, UI Retry repairs it, no duplicate versions |

## Prerequisites

- Backend venv present: `backend\.venv\Scripts\python.exe` (fastapi + uvicorn installed).
- Frontend deps installed (`frontend/node_modules` provides vite, @vitejs/plugin-vue and playwright).
- Playwright Chromium browser binaries. If missing, run once:

      cd frontend
      pnpm exec playwright install chromium

## Legacy scripts (historical only)

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

2026-09-08 additions: `structured-drafting.e2e.mjs` verifies save/discard/cancel when leaving a proposal and blocks navigation during acceptance. `scene-record-update.e2e.mjs` holds a record decision response to verify compilation stays disabled until acceptance completes. The latter also passed five consecutive local runs. `longform-benchmark.mjs` checks bounded history rows/options and measures the extra action of expanding prose; `--trace` records a separate CDP trace after the timed loop, and `--check-budgets` enforces the documented reference-host large-tier budgets. See [fix results](../docs/issues/2026-09-07-review/FIX-RESULT-2026-09-08.md).

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
