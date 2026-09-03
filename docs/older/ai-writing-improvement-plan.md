# AI Writing Studio 顺序改进执行手册

> 项目：`E:\projects\ai-writing`
>
> 基线日期：2026-08-26
>
> 面向对象：编程 AI / Coding Agent
>
> 目标：在不破坏现有可用 MVP 的前提下，按顺序把项目提升为状态可靠、业务闭环完整、可扩展且可长期维护的 Beta。

---

## 0. 当前基线

本计划以 2026-08-26 的实际代码和验证结果为准，不再执行旧计划中已经完成的事项。

当前已验证：

- Backend unittest：125 / 125 通过。
- Frontend tests：26 / 26 通过。
- Frontend ESLint：通过。
- Vue / TypeScript production build：通过。
- Ruff check / format check：通过。
- Real-browser E2E `full-review-loop.e2e.mjs`：通过。
- Real-browser E2E `wiki-failure.e2e.mjs`：通过。
- 当前核心能力已存在：数据库迁移、Unit of Work、事务型 Outbox 入队、统一 Review 状态机、Canon 乐观版本、分析幂等、结构化日志、备份恢复、真实浏览器 E2E、Provider Registry。

已知工作树注意事项：

- `backend/uv.lock` 是本次 review 验证过程中生成的未跟踪文件；除非某个任务明确决定正式采用该 lockfile，否则不要顺手提交。
- 不要把与当前任务无关的本地修改纳入提交。

当前产品阶段判断：

```text
Prototype                 ✅
Usable local MVP          ✅
Feature-complete PRD MVP  ◐
Reliable Beta             ◐
Production architecture   ❌
```

---

# 1. 编程 AI 执行协议

本节是整个计划的执行规则。每次只执行一个任务。

## 1.1 开始一个任务前

必须完成：

1. 阅读根目录 `AGENTS.md`。
2. 只阅读本文件中的“当前任务”和它明确引用的相关代码。
3. 执行 `git status --short`，记录既有未提交内容。
4. 对行为修复先写能暴露问题的回归测试，再改实现。
5. 不进行“顺手重构”；发现额外问题记录到本计划的后续任务，不扩大当前 scope。

## 1.2 一个任务的完成标准

只有同时满足以下条件，才能把任务从 `[ ]` 改为 `[x]`：

- 任务定义的业务不变量成立。
- 目标测试通过。
- 相关现有测试没有回归。
- Full gate 通过；若任务明确要求 E2E，则 E2E 也通过。
- `git diff --check` 无错误。
- Review 当前 diff，没有无关文件、调试代码、临时兼容分支或死代码。
- 形成一个独立提交；一个任务对应一个逻辑提交。

失败时停在当前任务，不开始下一个任务。

## 1.3 默认验证门禁

Backend：

```bash
python -m compileall backend/app
ruff check backend
ruff format --check backend
cd backend
python -m unittest discover -s tests
```

Frontend：

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

高风险任务额外执行：

```bash
cd frontend
pnpm test:e2e
```

高风险任务包括：

- Manuscript revision 提交语义。
- Outbox。
- Backup / Restore。
- Review / Write-back。
- 数据迁移。
- Provider runtime 公共边界。

---

# 2. 必须长期保持的业务不变量

后续所有实现都必须维护这些规则。

## INV-01 AI 只能提出变更，应用权属于应用和用户

AI 可以生成：

- Manuscript Proposal。
- Reference / Copilot Proposal。
- Canon / Memory Write-back Proposal。

AI Provider 不直接写最终 Canon、Memory 或 Manuscript 状态。

## INV-02 每个 committed Manuscript Revision 都进入同一提交后流水线

无论 Revision 来源是什么：

- 接受 AI Manuscript Proposal。
- 用户手工编辑正文并保存。
- Restore 历史 Revision。
- 后续 Copilot Apply。

一旦产生新的正式 Revision，就必须统一触发：

```text
Committed Revision
→ LLM Wiki index
→ Consistency analysis
→ Write-back analysis
→ 人工 Review
```

## INV-03 核心状态和派生状态分离

核心状态：

- Project。
- Snowflake Artifact。
- Canon。
- Memory。
- Scene Contract。
- Manuscript Scene / Revision。
- Review decision。

必须事务化保存。

派生状态：

- LLM Wiki 索引。
- Consistency report。
- 自动 Write-back 建议。
- Graph / Cognition 派生结果。

允许失败，但必须可重试、可恢复，失败不能回滚已提交的核心状态。

## INV-04 Review terminal state 不可逆

统一状态：

```text
pending_review
  ├─ accepted
  ├─ rejected
  └─ superseded
```

进入终态后不得转成其他状态。重复提交相同状态可以幂等返回。

## INV-05 跨存储恢复不能留下半恢复项目

Backup Import 成功后，SQLite 核心数据和 project modules 必须来自同一个 backup；失败后应保留导入前的可用状态。

---

# 3. 实施顺序总览

严格按以下顺序实施；P1 全部完成前不要进入 P2。

```text
P1-01 统一 Revision Commit Pipeline
  ↓
P1-02 Outbox 原子 Claim 与 Crash Recovery
  ↓
P1-03 Outbox Dispatcher 脱离 HTTP 请求
  ↓
P1-04 Backup Import 完整验证与跨存储恢复
  ↓
P1-05 Copilot 绑定正文 Selection 和来源版本
  ↓
P1-06 将 Copilot Proposal 安全应用为新 Revision
  ↓
P1-07 Copilot 一次生成多方案
  ↓
P2-01 Provider 选择去 DeepSeek 硬编码
  ↓
P2-02 Provider 按 Capability 拆接口
  ↓
P2-03 拆分 Frontend Manuscript / Reviews 大 Store
  ↓
P2-04 收窄 Backend Data Ports，消除 God Protocol
  ↓
P2-05 去除 Service 层 connection 泄漏
  ↓
P2-06 前端 API Error 与行为测试升级
  ↓
P2-07 扩充故障 / Provider / Recovery E2E
  ↓
P3-01 清理文档漂移、兼容 Shim 和测试 Harness
```

高级 Graph 可视化属于后续产品功能，不阻塞本计划。

---

# 4. P1：Reliable Beta 阻塞项

## [x] P1-01 统一 Committed Revision Pipeline

### 问题

当前接受 Manuscript Proposal 时：

`backend/app/data/flows.py`

会为新 Revision enqueue：

- `llm_wiki_ingest`
- `consistency_analysis`
- `writeback_analysis`

但以下两条真正的作者主路径只 enqueue Wiki：

- `restore_manuscript_revision()`
- `update_manuscript_scene()`

因此作者手工修改正文后，“保存正文 → 一致性检查 → Write-back Review”核心闭环断开。

### 目标

建立单一的“正式 Revision 已提交”业务流程。任何新 Manuscript Revision 都使用同一后置任务集合。

### 主要涉及

```text
backend/app/data/flows.py
backend/app/data/sqlite_store.py
backend/app/services/manuscript_service.py
backend/app/routers/manuscript.py
backend/app/outbox/handlers.py
backend/tests/test_manuscript_editing.py
backend/tests/test_post_accept_analysis.py
backend/tests/test_outbox.py
e2e/full-review-loop.e2e.mjs
```

### 实施步骤

1. 先增加回归测试：手工 edit 创建 Revision 后应存在三类 Outbox Job。
2. 增加回归测试：restore 创建新 Revision 后应存在三类 Outbox Job。
3. 提取一个唯一 helper / flow，例如：

```text
enqueue_committed_revision_jobs(revision)
```

它负责一次性 enqueue：

```text
llm_wiki_ingest
consistency_analysis
writeback_analysis
```

4. Proposal accept、manual edit、restore 全部调用该 helper。
5. 删除各调用点重复的 job 组合逻辑。
6. 确保每个新 Revision 的三类 job 各自只有一个，依赖现有 idempotency key 防重复。
7. 前端 manual save / restore 后刷新 Post-Acceptance Analysis 区域，使用户能看到正在执行或已完成的分析。

### 完成标准

给定任意一条产生正式 Revision 的路径：

```text
accept proposal
manual edit
restore revision
```

都满足：

- Manuscript version 正确 +1。
- 产生一个不可变 Revision。
- exactly one Wiki job。
- exactly one Consistency job。
- exactly one Write-back job。
- 自动分析生成的 Write-back 仍保持 `pending_review`，不会自动写 Canon / Memory。
- 重复请求不会产生重复 Revision 或重复 job。

### 必须验证

- Backend targeted tests。
- Backend full suite。
- Frontend tests/build。
- `pnpm test:e2e`。

### 提交建议

```text
Route every manuscript revision through post-commit analysis
```

---

## [x] P1-02 Outbox 原子 Claim 与 Crash Recovery

### 问题

当前 `OutboxRepository.transition()` 更新条件只有：

```sql
WHERE project_id = ? AND id = ?
```

并没有用当前状态做 CAS。

两个 dispatcher 如果同时读取到一个 `pending` job，理论上可以重复执行副作用。

另外：核心事务 commit 后、HTTP 同步 dispatch 前如果进程崩溃，job 会停在 `pending`；现有 retry API 只接受 `failed`，没有通用 crash recovery。

### 目标

让 Outbox 具备真正的：

- single-claim。
- crash recovery。
- stale-processing recovery。
- 幂等 retry。

### 主要涉及

```text
backend/app/data/repositories/outbox.py
backend/app/outbox/service.py
backend/app/outbox/models.py
backend/app/data/migrations.py
backend/tests/test_outbox.py
backend/tests/test_migrations.py
```

### 实施步骤

1. 先写并发 claim 回归测试：两个 service / connection 同时 claim 同一 pending job，只有一个成功。
2. 将 claim 变成原子状态转换：

```sql
UPDATE outbox_jobs
SET status = 'processing', ...
WHERE project_id = ?
  AND id = ?
  AND status = 'pending'
```

只有 `rowcount == 1` 的调用方可以执行 handler。
3. 不再把 `processing` job 当成普通可执行 job 直接再次 `_run()`。
4. 增加 processing 开始时间字段，例如 `processing_started_at`，通过正式 migration 添加。
5. 增加 stale-processing recovery：超过租约时间的 `processing` job 可安全恢复为 `pending`。
6. retry `failed -> pending` 同样使用条件更新，避免两个 retry 请求重复运行。
7. 为 pending crash recovery 提供 service API：应用重启后能继续处理数据库中遗留 pending job。

### 完成标准

- 两个并发 claim 只有一个 handler 被调用。
- pending job 跨进程重启仍可执行。
- stale processing job 能恢复。
- succeeded job 永远不会重新执行。
- failed job retry 后 attempt_count 正确增加。
- handler 抛错仍不会影响核心业务事务。

### 必须验证

- Migration tests。
- Outbox concurrency / recovery tests。
- Backend full suite。
- E2E 保持通过。

### 提交建议

```text
Make outbox claiming atomic and recoverable
```

---

## [ ] P1-03 Outbox Dispatcher 脱离 HTTP 请求

### 问题

现在所谓 Outbox 在事务层是异步思路，但执行仍发生在请求路径：

```text
HTTP mutation
→ DB commit
→ process_pending/process_job
→ handler IO
→ HTTP response
```

实际测试中曾出现 Wiki handler 约 1.34 秒，使接受 Proposal 的 HTTP 请求约 1.55 秒。

随着 Provider / Index / Analysis 变复杂，请求延迟和失败耦合会继续增加。

### 目标

建立本地优先、单进程可运行的 app-owned Outbox Dispatcher，使 HTTP mutation 只负责可靠入队，不等待副作用执行。

### 约束

- 当前是 local-first MVP，不引入 Redis、Celery、Kafka 等外部基础设施。
- 复用 P1-02 的 CAS claim 和 recovery。
- Dispatcher 必须在应用进程重启后自动处理 pending job。

### 主要涉及

```text
backend/app/main.py
backend/app/outbox/service.py
backend/app/outbox/
backend/app/services/snowflake_service.py
backend/app/routers/manuscript.py
backend/app/routers/snowflake.py
backend/app/outbox/http.py
frontend/src/stores/reviews.ts
frontend/src/stores/manuscript.ts
backend/tests/test_outbox.py
e2e/full-review-loop.e2e.mjs
e2e/wiki-failure.e2e.mjs
```

### 实施步骤

1. 在 FastAPI lifespan 中启动一个 app-owned dispatcher loop。
2. 新 job 入队后只 signal / wake dispatcher，不同步运行 handler。
3. dispatcher 定期 sweep pending，并优先响应 wake signal。
4. 同步 handler 通过 worker thread / `asyncio.to_thread` 等方式运行，避免阻塞 event loop。
5. shutdown 时停止领取新 job，并有界等待当前任务完成或安全留下可恢复状态。
6. 移除 mutation route 中直接 `process_pending()` / `process_job()` 的执行耦合。
7. 修改响应语义：HTTP 只报告 job 已 scheduled/pending，不假装副作用已经完成。
8. 前端继续通过现有 Outbox / Analysis 面板轮询状态。
9. 启动应用时自动恢复 P1-02 遗留 pending / stale processing。

### 完成标准

- 人为让 handler sleep 1 秒，mutation HTTP 请求不再额外等待约 1 秒。
- mutation 返回后 job 最终自动变为 succeeded / failed。
- backend restart 后遗留 pending 自动被消费。
- wiki failure 仍不会影响已提交 Manuscript。
- UI 可以看到 pending → processing → succeeded/failed。
- Retry UI 继续有效。

### 必须验证

- Backend dispatcher tests。
- Backend full suite。
- 两套 real-browser E2E。

### 提交建议

```text
Dispatch outbox jobs outside request latency
```

---

## [ ] P1-04 Backup Import 完整验证与跨存储一致性

### 问题

当前 import 顺序大致是：

```text
验证部分 package
→ SQLite transaction 完成
→ 删除旧 project modules
→ 逐文件恢复 modules
```

若数据库已经提交后，module 恢复失败，会留下：

```text
新数据库 + 丢失/半恢复 modules
```

另外 module path 安全检查发生在数据库 mutation 之后，过晚。

### 目标

Backup Import 在任何失败点都不能把原项目变成半恢复状态。

### 主要涉及

```text
backend/app/services/backup_service.py
backend/app/routers/backup.py
backend/tests/test_backup.py
backend/app/data/migrations.py   # 仅当需要 metadata，不强制
frontend/src/stores/backups.ts
```

### 实施步骤

#### A. Mutation 前完整验证

在修改数据库和文件系统前一次性验证：

- manifest kind / format / schema version。
- manifest project id / title。
- table 名称白名单。
- 每个 table row 的列集合。
- 每条 project-scoped row 的 `project_id` 必须等于 manifest project id。
- `projects` 只能包含目标 project 根记录。
- manifest row_counts 与实际数据一致。
- 所有 module entry path 先完成 Zip Slip / `..` / absolute path 校验。
- module 文件可完整解码/读取。
- package / entry / uncompressed total 有合理上限，避免异常 ZIP 消耗本机资源。

任何验证失败：数据库和现有 modules 必须零变化。

#### B. 文件先 staging

把新 module 内容完整写入与目标同文件系统的 temporary staging directory。

只有 staging 全部成功才进入 replace 阶段。

#### C. 可回滚 swap

建议流程：

```text
validate
→ stage new modules
→ begin SQLite UoW
→ replace DB rows
→ rename old modules to backup location
→ atomic rename staged modules to target
→ commit DB
→ delete old module backup
```

任一步失败：

- rollback DB transaction。
- 恢复 old module directory。
- 清理 staging。

不要用“DB commit 后再逐文件写”的方式。

### 完成标准

至少有故障注入测试覆盖：

1. invalid module path → 零 mutation。
2. bad project_id row → 零 mutation。
3. staging write failure → 零 mutation。
4. filesystem swap failure → DB rollback + old modules intact。
5. DB failure after filesystem prepare → old modules 恢复。
6. 正常 overwrite → DB 和 modules 都来自同一个 package。
7. 正常导入后再次 export，关键 row count / module count 一致。

### 必须验证

- Backup dedicated tests。
- Backend full suite。
- Frontend backup contract/behavior tests。
- Full E2E 至少保持原 happy path 通过。

### 提交建议

```text
Make project restore validated and rollback-safe
```

---

# 5. P1：补齐 PRD 核心 Copilot 闭环

## [ ] P1-05 Copilot 绑定正文 Selection 和来源版本

### 问题

当前 References / Copilot 是独立表单：

- 手工选 `scope_type`。
- 手工填写 `scope_ref`。
- 手工描述 writing problem。

它不知道用户实际选中的正文，也没有记录建议基于哪个 Manuscript version 生成。

如果正文在生成建议后发生变化，系统无法判断建议是否已 stale。

### 目标

让正文编辑器成为 Copilot 的入口，并为每条 suggestion 保存可验证的 source provenance。

### 设计要求

增加一个结构化来源模型，例如：

```text
ReferenceSelectionContext
- scene_id
- revision_id / scene_version
- selection_start
- selection_end
- selected_text
- selected_text_hash
```

具体字段名可以根据现有 schema 调整，但必须能回答：

> 这条建议是基于哪一个正文版本、哪一段文字生成的？

### 主要涉及

```text
backend/app/models.py
backend/app/data/migrations.py
backend/app/data/repositories/review.py
backend/app/agents/reference_workflow.py
backend/app/services/reference_service.py
frontend/src/components/manuscript/ReferenceWorkspace.vue
frontend/src/components/manuscript/*Editor*.vue 或当前正文 textarea 所在组件
frontend/src/stores/reviews.ts
frontend/src/stores/manuscript.ts
frontend/src/types/index.ts
backend/tests/test_reference_generation.py
frontend/tests/
```

### 实施步骤

1. 前端捕获当前正文 textarea/editor 的 selectionStart / selectionEnd 和 selected text。
2. 打开 Copilot 时自动填充 manuscript scene scope，不要求用户复制 scene id。
3. Reference generation request 携带 SelectionContext。
4. backend 校验 selection 属于指定 current revision / version。
5. suggestion 持久化来源 context，而不是只保存自由文本 `used_context`。
6. provider/local workflow 都把 selected text 和 Scene Contract/Canon context 一起用于建议生成。
7. UI 明确显示建议来源，例如：

```text
Scene X · v3 · selected 146–302
```

### 完成标准

- 用户选中正文后可以直接发起 Copilot。
- 后端持久化 suggestion 与具体 scene/version/selection 的绑定。
- 切换 project / scene 后异步旧结果不会写入当前项目。
- 未选择正文时仍可保留 project/scene 级 brainstorm 模式。
- 当前任务不自动修改正文；Apply 留给 P1-06。

### 提交建议

```text
Bind reference suggestions to manuscript selections
```

---

## [ ] P1-06 将 Copilot Proposal 安全应用为新 Revision

### 问题

当前 `Accept Reference` 只更新 Review status，不会把建议应用到正文，因此 PRD 的“采纳建议”没有闭环。

直接把 suggestion content 覆盖正文同样不可接受，因为生成建议后正文可能已经被用户修改。

### 目标

增加显式、安全、可追踪的 Apply 操作。Apply 后产生一个新的 Manuscript Revision，并自动进入 P1-01 的统一后置流水线。

### 业务规则

1. Review 和 Apply 是两个不同动作。
2. suggestion 必须处于 `accepted` 才允许 Apply。
3. Apply 前验证：
   - current scene version == suggestion source version。
   - selection range 仍有效。
   - selected text / hash 仍匹配。
4. stale suggestion 返回 409，不静默覆盖新正文。
5. Apply 通过 Manuscript application service / revision flow，不允许 Reference repository 直接 UPDATE manuscript table。
6. Apply 是幂等的；同一 suggestion 不产生两个 Revision。

### 建议 API

可采用等价设计，例如：

```text
POST /projects/{project_id}/references/suggestions/{suggestion_id}/apply
```

首版只支持：

```text
replace selected text
```

不要在同一任务加入复杂 patch DSL。

### 建议持久化

为 suggestion 或独立 application record 保存：

```text
applied_revision_id
applied_at
```

以便审计和幂等 replay。

### 完成标准

- Accepted suggestion 可替换其来源 selection。
- Apply 产生 Manuscript version +1。
- 新 Revision 被保存。
- 自动 enqueue Wiki + Consistency + Write-back 三类 job。
- 再次 Apply 同一 suggestion 不产生重复 Revision。
- 正文版本已变化时返回 conflict，并保留用户的新正文。
- UI 能显示“Applied in revision vN”或冲突原因。

### 必须验证

- Backend apply happy path。
- stale version conflict。
- changed selection conflict。
- idempotent replay。
- full review loop E2E 增加一次 Copilot apply。

### 提交建议

```text
Apply accepted references as safe manuscript revisions
```

---

## [ ] P1-07 Copilot 一次生成多方案

### 问题

PRD 要求 Copilot 对卡点提供“多套结构化参考建议”。当前一次 generation 主要得到单条 ReferenceSuggestion。

### 目标

一次用户请求得到一个可比较的 suggestion group，默认 3 个明显不同的方案。

### 约束

- 不改变 P1-06 的 Apply 安全语义。
- 每个 option 仍然是独立 reviewable suggestion。
- options 共享 generation group 和相同 SelectionContext。

### 设计建议

增加：

```text
generation_group_id
option_index
```

或等价结构。

API 可以返回 `list[ReferenceSuggestion]` 或一个 group response；选择对现有客户端迁移成本最低的方案。

### 完成标准

- 默认生成 3 个方案。
- UI 同组并排/列表比较，不混入其他历史请求。
- 每个方案可独立 Accept / Reject。
- 只能 Apply 被接受的具体 option。
- Provider 输出少于/多于目标数量时有清晰 normalization，不产生空 suggestion。

### 提交建议

```text
Generate grouped copilot options for review
```

---

# 6. P2：Provider 可扩展性

## [ ] P2-01 Provider 选择去 DeepSeek 硬编码

### 问题

已有 `ProviderRegistry`，但多个 Service 仍直接：

```python
registry.create("deepseek", ...)
```

主要位置：

```text
backend/app/services/manuscript_service.py
backend/app/services/reference_service.py
backend/app/services/writeback_service.py
backend/app/services/snowflake_service.py
```

因此增加第二个外部 Provider 时仍需修改多个业务 Service。

### 目标

Service 只表达：

```text
我要一个 manuscript/reference/writeback/snowflake provider
```

不表达：

```text
我要 DeepSeek
```

### 实施步骤

1. 在 integrations 层增加单一 Provider Resolver / Policy。
2. 明确两种语义：
   - preferred：外部 Provider 可用则使用，否则 local fallback。
   - external：只解析已配置的外部 Provider；没有则返回 not configured。
3. `*/provider` 现有 API 首先保持兼容，但内部不出现 provider name。
4. runtime status 从同一个 resolver 读取，避免状态和实际执行策略漂移。
5. 用 fake registry/provider 测试：注册一个非 DeepSeek provider 后，Service 无需修改即可使用。

### 完成标准

`backend/app/services/` 中业务 Service 不再出现：

```text
"deepseek"
DeepSeekSettings
DeepSeekWritingWorkflow
```

具体 provider 名只存在 integrations/configuration 层。

### 提交建议

```text
Resolve writing providers outside application services
```

---

## [ ] P2-02 Provider 按 Capability 拆接口

### 问题

当前 `WritingProvider` 要求同一个 Provider 同时实现：

- Snowflake。
- Manuscript。
- Reference。
- Write-back。

这会阻碍“某 provider 只适合一种能力”的扩展，也会产生无意义 stub。

### 目标

把能力变成明确接口，而不是强迫所有 provider 实现整个胖协议。

### 设计方向

可采用结构化 Protocol：

```text
SnowflakeGenerationProvider
ManuscriptGenerationProvider
ReferenceGenerationProvider
WritebackGenerationProvider
```

Registry / Resolver 能查询 capability。

### 完成标准

- 一个只实现 Manuscript capability 的 fake provider 可以注册并用于 Manuscript。
- 它不需要实现 Snowflake / Write-back 空方法。
- Resolver 在 capability 不支持时返回明确配置/能力错误。
- 业务模型中不暴露 SDK-specific types。

### 提交建议

```text
Split provider interfaces by generation capability
```

---

# 7. P2：Frontend 高内聚改造

## [ ] P2-03 拆分 Manuscript / Reviews 大 Store

### 问题

当前文件规模约为：

```text
frontend/src/stores/manuscript.ts  > 1000 lines
frontend/src/stores/reviews.ts       ~675 lines
```

`manuscript.ts` 同时承担：

- Chapter CRUD。
- Scene Contract CRUD。
- Compile。
- Draft proposal。
- Proposal review。
- Manuscript editing。
- Revision / diff / restore。
- Export。
- Draft autosave。
- Graph refresh。
- Reviews refresh。

这是第二次形成新的“大 workspace store”。

### 目标

按业务生命周期拆 Store，同时避免 Store-to-Store 形成循环依赖图。

### 建议边界

```text
stores/manuscript/
  chapters.ts
  sceneContracts.ts
  drafts.ts
  revisions.ts
  coordinator.ts

stores/reviews/
  writebacks.ts
  references.ts
  analysis.ts
  coordinator.ts
```

保留一个很薄的 compatibility facade 只在迁移期间使用；完成后删除无价值 facade。

### 约束

- 业务行为不变。
- 不和 UI redesign 放在同一个提交。
- 跨 domain 刷新放 coordinator / workspace orchestration，不让 leaf store 任意 import 其他 leaf store。
- 共享 draft session/request scope 继续使用现有 service/composable。

### 完成标准

- `manuscript.ts` 不再是 >1000 行的多职责 Store。
- `reviews.ts` 不再同时拥有 Reference、Write-back、Analysis 三条完整工作流。
- leaf store 之间没有循环 import。
- workspace 只负责真正的跨域协调。
- 当前组件功能和 E2E 行为不变。

### 提交建议

```text
Split manuscript and review stores by workflow ownership
```

---

# 8. P2：Backend 低耦合改造

## [ ] P2-04 收窄 Backend Data Ports，消除 God Protocol

### 问题

`backend/app/data/interfaces.py` 的 `WritingDataStore` 同时描述 Project、Snowflake、Canon、Memory、Scene、Manuscript、Review、Analysis 等几乎全部数据能力。

Service 因此在类型层依赖整个系统，而不是自己真正需要的最小能力。

### 目标

使用窄接口表达 Service 依赖，同时暂时允许同一个 `SQLiteWritingDataStore` 实例实现多个 Protocol，降低迁移成本。

### 建议方向

例如：

```text
ProjectReader
SnowflakeStore
CanonStore
SceneStore
ManuscriptStore
ReviewStore
AnalysisStore
OutboxStore
```

也可以按 read/write 使用场景进一步组合，但不要为了抽象而制造几十个单方法接口。

### 实施顺序

1. 从一个 Service 开始，例如 `ManuscriptService`。
2. 定义它真正需要的 port 组合。
3. 保持 runtime object 不变，只收窄类型依赖。
4. 测试通过后再依次迁移 Writeback、Reference、Snowflake。
5. 最终移除无人依赖的 God Protocol。

### 完成标准

- 每个 Service 的 constructor type 能直接看出业务依赖。
- 新增 Canon-only service 不需要看到 Manuscript/Outbox 方法。
- 不修改数据行为。
- 不引入 repository locator/service locator。

### 提交建议

```text
Narrow data ports around application service needs
```

---

## [ ] P2-05 去除 Service 层 connection 泄漏

### 问题

当前部分 store API 暴露：

```python
connection: object | None = None
```

`SnowflakeCompileService` 等代码还直接使用：

```text
data_store.connect()
record_analysis_run(connection, ...)
create_scene_proposals(..., connection=connection)
```

这让应用层知道 SQLite transaction 组合方式，削弱数据接口抽象。

### 目标

事务组合由 Data/UoW 层拥有；Service 表达“执行一个业务事务”，不传底层 connection。

### 实施方向

将跨 aggregate transaction 继续集中到：

```text
app.data.flows
SqliteUnitOfWork
```

或增加窄的 application transaction ports。

不要把 SQL 移回 Service。

### 完成标准

- Service 和 Router 不再传 `sqlite3.Connection` / `object connection`。
- 公共 Data Port 不暴露 SQLite connection 参数。
- 跨 aggregate 操作仍保持单事务。
- UnitOfWork tests 继续证明 rollback / commit 行为。

### 提交建议

```text
Keep transaction composition inside the data layer
```

---

# 9. P2：测试与前端错误处理

## [ ] P2-06 前端 API Error 与行为测试升级

### 问题 A：错误信息不一致

部分 Store 已使用 `readErrorDetail()`，部分仍把所有非 2xx / exception 转成：

```text
Check that the API is running.
```

这会把真实的：

- 409 version conflict。
- 422 validation error。
- 501 provider unavailable。

隐藏成同一个泛化提示。

### 问题 B：很多前端测试是源码正则 Contract Test

例如 draft safety 主要通过 `readFileSync + assert.match` 验证某段代码存在。

这适合架构约束，但不能证明真实 Pinia 状态行为。

### 目标

- API 错误保留 backend detail / status / request id。
- 高价值状态流程由行为测试证明，而不是只检查源码字符串。

### 实施步骤

1. 扩展 `ApiError`：至少携带 `status`、可展示 detail、`x-request-id`。
2. `fetchJson` / shared client 统一解析 FastAPI error body。
3. 逐步替换 Store 中重复的 raw `response.ok` + generic catch。
4. 不要求一次迁移整个前端；从 Manuscript/Reviews 高风险 mutation 开始。
5. 增加 Vite-native behavior test runner；优先最小依赖。若采用 Vitest，先只加 Vitest，不同时引入大型 UI 测试栈。
6. 将以下高价值 contract tests 增加真正行为测试：
   - dirty editor 切换取消。
   - cached draft restore。
   - project switch stale response 被忽略。
   - proposal accept 后依赖集合刷新。
   - 409 write-back / Copilot conflict 正确显示。
   - backup preview → overwrite confirm。
7. 保留少量真正有价值的架构 contract tests，例如“Router 不 import provider SDK”。

### 完成标准

- 409/422/501 在 UI 有不同、可行动的错误提示。
- 至少上述关键状态流程由 executable behavior tests 覆盖。
- 不再依赖正则测试来证明核心业务行为。

### 提交建议

```text
Make frontend errors actionable and tests behavioral
```

---

## [ ] P2-07 扩充故障 / Provider / Recovery E2E

### 目标

让 E2E 不只证明 happy path，也证明系统的核心可靠性承诺。

### 必须新增的场景

#### 1. Outbox startup recovery

预置一个 pending job，启动 backend 后验证自动完成。

#### 2. Manual edit post-analysis

浏览器编辑 accepted manuscript，保存 v2，验证三类 post-commit jobs 和 Consistency/Write-back UI。

#### 3. Restore post-analysis

Restore 历史版本产生新 revision，验证同一 pipeline。

#### 4. Copilot selection → accept → apply

覆盖 P1-05 / P1-06 的用户主路径。

#### 5. Provider-backed path，无公网依赖

在 E2E harness 启动一个本地 OpenAI-compatible fake HTTP server，把 DeepSeek base URL 指向它。

目标是测试真实：

```text
provider config
→ concrete DeepSeek adapter
→ HTTP request/response parsing
→ provider proposal
→ review
```

而不是 route mocking，也不依赖真实 API key。

#### 6. Provider malformed response

fake provider 返回非法 structured data，验证 502/422、无脏 proposal。

### Harness 清理

当前两套 E2E PASS，但 teardown 偶尔出现：

```text
vite close timed out after 8s; continuing teardown
```

定位子进程/handle 未正常关闭的原因，做到成功执行无 teardown warning。

### 完成标准

- CI 仍无需任何真实 Provider key。
- E2E 对核心故障恢复有可重复证明。
- 所有 child process 正常结束。

### 提交建议

```text
Cover recovery and provider paths in live E2E
```

---

# 10. P3：维护性收尾

## [ ] P3-01 清理文档漂移、兼容 Shim 和过时描述

### 当前已知漂移

README 中 Browser E2E 仍有“optional, local only”等历史表述，但开发计划已经说明它是 CI merge-blocking gate。

存在一些迁移后 compatibility shim，例如：

```text
backend/app/data/mixins/scene_proposals.py
```

Router 仍通过旧路径 import exception。

### 目标

代码进入稳定结构后再删 shim，避免在前面高风险任务中混入无意义 churn。

### 实施步骤

1. 搜索 README / development-plan 与当前 CI/scripts 不一致的描述。
2. 删除已经没有消费者的 compatibility import path。
3. 删除迁移后确认无引用的 legacy helper。
4. 文档只记录长期架构、不缓存一条命令即可从 package/config 找到的信息。
5. 更新本文件：已完成任务改 `[x]`，保留关键 architecture decision，不保留过时实施细节。

### 完成标准

- README、AGENTS、development-plan、CI 对验证门禁描述一致。
- 无仅为旧 import 路径保留且已无使用方的 shim。
- `rg "legacy|compatibility shim" backend/app` 的剩余结果都有明确保留理由。

### 提交建议

```text
Remove stale architecture compatibility and docs drift
```

---

# 11. 暂不实施的事项

以下事项在 Reliable Beta 之前不要插队：

- 高级 Graph visualization。
- GraphRAG 大规模升级。
- 新 Agent orchestration framework。
- LangGraph 重构。
- 云同步。
- 多人协作。
- 新编辑器框架整体替换。
- 为“未来可能需要”增加大型基础设施依赖。

如果新需求与本计划冲突，优先维护第 2 节的业务不变量。

---

# 12. 每个任务的 AI Handoff 模板

编程 AI 完成一个任务后，必须用以下格式汇报，随后停止，等待下一次任务指令：

```markdown
## Completed: <task id + title>

### Behavior changed
- ...

### Files changed
- ...

### Tests added/updated
- ...

### Verification
- `<command>` — PASS
- `<command>` — PASS

### Architecture notes
- 哪个不变量现在由哪里保证。

### Remaining risks
- 只记录当前 task 无法合理解决的问题；不要顺手继续实现。

### Next task
- <next task id>，未开始。
```

---

# 13. 最终验收：何时可以称为 Reliable Beta

只有以下全部成立，才完成本计划的 P1 阶段：

- [ ] 所有 committed Manuscript Revision 都进入相同 post-commit pipeline。
- [ ] Outbox 使用原子 claim，不会因并发 dispatcher 重复执行同一 job。
- [ ] pending / stale-processing 能跨 backend restart 自动恢复。
- [ ] Outbox handler 不再增加 mutation HTTP 请求延迟。
- [ ] Backup Import 的 DB + modules 在故障下不会半恢复。
- [ ] Copilot 能从正文 selection 发起建议。
- [ ] Copilot suggestion 能安全 Apply 为新 Revision。
- [ ] Apply 遇到 stale manuscript version 会冲突而不是覆盖。
- [ ] Copilot 一次提供多方案供用户选择。
- [ ] Backend full suite 全绿。
- [ ] Frontend lint/test/build 全绿。
- [ ] Live E2E 全绿。

完成这些后，再进入 P2 架构收敛；不要把结构重构提前到可靠性修复之前。
