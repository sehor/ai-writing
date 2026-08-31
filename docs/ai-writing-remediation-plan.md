# AI Writing Studio 审查整改计划

> 审查基线：`integration-graphify-clp`
>
> 基线提交：`42dd63f`（`test: certify narrative graph clp completion`）
>
> 编制日期：2026-08-31
>
> 审查维度：代码质量、业务逻辑、产品完成度

## 1. 文档目的

本计划用于把当前项目从“后端领域能力较完整、前端和跨层集成尚未收口的内部开发版”，推进到“数据安全、核心写作闭环可用、架构可持续演进、CI 可作为发布门禁”的本地优先 MVP。

整改遵循以下顺序：

1. 先消除可能损坏用户作品的数据风险。
2. 再修复前后端契约漂移和异步任务不可见问题。
3. 在继续扩展产品功能前，处理循环依赖、超大模块和分层泄漏。
4. 完成长篇作者真正需要的编辑、Copilot 和 Review 工作台。
5. 最后处理大项目性能、分页和运维能力。

本计划不改变项目的核心产品原则：

- SQLite Narrative Domain 是唯一权威故事状态。
- Graph、LLM Wiki、Cognition 和 CLP 都是可重建或可失败的派生能力。
- AI 和外部工具只能生成提案，不能绕过校验与人工 Review 修改权威状态。
- Canon、Memory / Style、Manuscript、Narrative Graph 的职责继续保持分离。

## 2. 当前基线

| 检查项 | 当前状态 | 说明 |
|---|---|---|
| Git 工作区 | 干净 | 审查未修改代码 |
| 后端测试 | 203 项通过 | 在安装完整 `requirements.txt` 依赖的 Python 环境中通过 |
| Python compileall | 通过 | 后端源码可编译 |
| Ruff lint | 通过 | 当前只启用基础错误规则 |
| Ruff format | 未通过 | 13 个文件需要格式化 |
| 前端 ESLint | 通过 | 无 lint 阻断 |
| 前端源码契约测试 | 27 项通过 | 多数为 `readFileSync + regex`，不能替代行为测试 |
| 前端生产构建 | 通过 | Vue TypeScript 构建成功 |
| Full Review Loop E2E | 未通过 | UI 任务状态刷新和测试等待条件存在竞态 |
| Wiki Failure E2E | 未通过 | 测试在任务进入终态前断言状态 |
| 备份 / 恢复 | 存在发布阻断 | 会遗漏 Narrative Domain 表，失败路径不是原子的 |
| Narrative / CLP 前端接入 | 未收口 | 后端已实现，前端类型、状态面板和 Review UI 不完整 |

## 3. 整改目标

整改完成后，系统至少应满足以下目标：

### 3.1 数据安全

- 项目备份覆盖全部项目级权威数据。
- 导入失败不会部分覆盖数据库，也不会删除旧模块文件。
- 旧备份包的兼容性和数据缺失风险对用户明确可见。
- 任何覆盖导入都可以在失败时恢复到导入前状态。

### 3.2 业务闭环

- 正文正式提交后，Wiki、Consistency、Writeback、CLP 四类任务都可观察、可重试。
- Narrative Relation 和 StoryThread 生命周期提案可以在前端正确审阅。
- 用户重新打开项目后仍能看到历史失败和进行中的任务。
- AI 草稿在进入正式 Manuscript 前可以编辑。
- Copilot 建议可以作用于正文选区或草稿，而不只是改变建议状态。

### 3.3 代码质量

- 前端领域 Store 不再相互循环依赖。
- 应用服务不依赖 FastAPI 类型，集成层不反向依赖服务层。
- 超大 Store、DTO 和数据门面按业务边界拆分。
- Python 运行时依赖只有一个真相源。
- 前端测试以 Store 和组件行为为主，源码正则测试仅保留少量边界检查。

### 3.4 发布质量

- Backend、Frontend、Browser E2E 和 Repository Hygiene CI 全绿。
- 连续多次运行 E2E 不依赖偶然的任务执行时序。
- PRD 的结构化起草、Copilot 辅助、保存分析与人工写回三条核心场景均有真实浏览器覆盖。

## 4. 优先级和发布策略

| 优先级 | 定义 | 发布策略 |
|---|---|---|
| P0 | 数据损坏、静默数据丢失、失败后部分提交 | 未关闭前不得发布，也不得默认开放覆盖导入 |
| P1 | 核心业务不可见、跨层契约错误、架构持续恶化、CI 红灯 | 必须在 MVP 发布前关闭 |
| P2 | 作者工作台和核心交互完成度不足 | MVP 应完成；可按垂直场景逐步交付 |
| P3 | 大项目性能、分页、可观测性增强 | MVP 后持续改进，不阻断首个可用版本 |

建议在 P0 和 P1 完成前冻结新的 Provider、Graph 算法和大型功能扩展。修复期间只接受与数据安全、契约收口、测试门禁和架构拆分直接相关的变更。

## 5. 总体阶段计划

以下工作量是单名熟悉项目的全栈工程师粗略估计，用于排序，不作为承诺日期。

| 阶段 | 工作流 | 建议工作量 | 前置依赖 | 阶段输出 |
|---|---|---:|---|---|
| Phase 0 | 备份完整性与原子恢复 | 3–5 人日 | 无 | 数据安全阻断项关闭 |
| Phase 1A | 跨层契约与 Outbox 任务闭环 | 4–7 人日 | Phase 0 可并行部分工作 | CLP/Narrative 前端可观察、可审阅 |
| Phase 1B | 代码质量专项整改 | 7–12 人日 | 先确定共享契约边界 | 消除循环依赖，恢复分层和高内聚 |
| Phase 1C | 测试与 CI 恢复 | 3–6 人日 | 1A/1B 持续同步 | 所有必跑门禁全绿 |
| Phase 2 | 作者工作台和产品闭环 | 10–15 人日 | Phase 1 完成 | 可编辑草稿、Copilot Apply、三栏工作台 |
| Phase 3 | 长篇规模化与运维 | 持续 | Phase 2 | 分页、性能、指标和故障诊断 |

## 6. Phase 0：备份与恢复数据安全

### P0-01：建立完整的项目权威数据清单

**问题**

`backend/app/services/backup_service.py` 的 `TABLES_IN_ORDER` 是手工清单，当前未包含以下项目级 Narrative Domain 表：

- `story_facts`
- `knowledge_states`
- `story_fact_character_knowledge`
- `narrative_relations`
- `story_threads`
- `story_thread_events`

覆盖导入会级联删除这些数据，却不会恢复，接口仍可能返回成功。

**整改任务**

- [ ] 将全部项目级权威表加入备份和恢复顺序。
- [ ] 明确表之间的外键插入顺序，尤其是 `story_fact_character_knowledge` 和 `story_thread_events`。
- [ ] 增加自动完整性检查：数据库中出现新的 `project_id` 表时，如果未声明备份策略，测试必须失败。
- [ ] 在 Manifest 中记录权威表集合和每张表的行数。
- [ ] 对导出后的行数和 Manifest 行数做一致性校验。

**主要涉及文件**

- `backend/app/services/backup_service.py`
- `backend/app/data/migrations.py`
- `backend/tests/test_backup.py`

**验收标准**

- 创建包含 StoryFact、KnowledgeState、NarrativeRelation、StoryThread 和 ThreadEvent 的项目。
- 导出、删除、重新导入后，所有记录逐字段一致。
- 覆盖导入后，上述记录不丢失。
- 新增一张带 `project_id` 的表但不更新备份策略时，CI 明确失败。

### P0-02：所有包校验必须发生在写入前

**问题**

当前项目 ID 和模块路径在数据库事务提交后才被完整检查。恶意或损坏包可能使导入接口抛错，但数据库已经写入。

**整改任务**

- [ ] 在打开写事务前校验 `project.id`，只允许项目 ID 规范中的安全字符。
- [ ] 校验 `data.json` 中每张表、每个列名和每行的 `project_id`。
- [ ] 所有非 `projects` 表的 `project_id` 必须等于 Manifest 项目 ID。
- [ ] 所有模块路径先标准化，再验证不能绝对化、不能包含 `..`、不能逃逸临时根目录。
- [ ] 校验文件编码、重复 ZIP 成员、压缩包大小和解压后大小上限。
- [ ] 校验 Manifest 行数、实际行数和模块文件数。
- [ ] 在 Preview 阶段执行和 Import 相同的完整校验。

**验收标准**

对以下包执行 Preview 和 Import，数据库及项目文件都保持完全不变：

- 非法项目 ID。
- `modules/../escape.txt`。
- 未知表或未知列。
- 子表项目 ID 与 Manifest 不一致。
- Manifest 行数不一致。
- 重复 ZIP 文件名。
- 非 UTF-8 模块文件。

### P0-03：实现数据库和模块文件的可回滚恢复

**问题**

当前数据库事务先提交，随后删除旧模块目录并写文件，数据库和文件系统不是一个一致性操作。

**整改方案**

建议采用“预校验 + 临时目录 + 旧目录保留 + 数据库事务 + 原子目录切换”的方式：

```text
读取 ZIP
→ 完整校验
→ 解压模块到项目根之外的临时目录
→ 校验临时目录
→ 将旧模块目录改名为 backup 目录
→ 开启 SQLite UnitOfWork
→ 删除并恢复项目权威表
→ 原子切换临时模块目录为正式目录
→ 提交数据库事务
→ 删除 backup 目录
```

任何步骤失败时：

```text
数据库 rollback
+ 删除临时目录
+ 将 backup 目录恢复为正式目录
```

如果目标平台无法保证数据库事务和目录重命名的绝对原子性，应显式实现补偿事务，并用故障注入测试覆盖每一个切换点。

**整改任务**

- [ ] 文件先写入临时目录，不直接写正式目录。
- [ ] 覆盖时不先 `rmtree`，旧目录必须保留到整个流程成功。
- [ ] 对目录 rename、数据库 insert、commit 前后注入异常并验证回滚。
- [ ] 导入结果中返回恢复格式版本和完整性校验摘要。

**验收标准**

在下列位置人为抛出异常，原数据库和原模块目录必须保持逐字节一致：

- 删除旧项目记录后。
- 插入一半数据后。
- 临时目录准备完成后。
- 旧目录重命名后。
- 新目录切换前后。
- 数据库 commit 前。

### P0-04：备份格式升级和旧包策略

**整改任务**

- [ ] 将备份格式升级为 v2，记录完整权威表清单和必要校验信息。
- [ ] v1 包在 Preview 中显示 `legacy_incomplete` 风险提示。
- [ ] 默认禁止使用 v1 包覆盖已有项目。
- [ ] 导入 v1 为新项目时，明确提示其可能不含 Narrative Domain 数据。
- [ ] 前端覆盖确认文案区分“普通覆盖”和“旧格式不完整覆盖”。

**发布门禁**

在 P0-01 至 P0-04 完成前，覆盖导入按钮应被隐藏、禁用或标记为实验能力，不能作为可靠备份功能宣传。

## 7. Phase 1A：跨层契约与 Outbox 闭环

### P1-01：建立单一 API 契约来源

**问题**

当前后端 Pydantic Literal、前端 TypeScript Union、UI 过滤数组和源码正则测试分别维护同一套业务枚举，已经发生漂移：

- 后端有 `clp_extraction`，前端没有。
- 后端 WritebackTarget 有 `narrative_relation`、`story_thread_status`，前端没有。
- 后端 OutboxJob 有 `processing_started_at`，前端类型没有。

**整改任务**

- [ ] 以 FastAPI OpenAPI 为 API 契约真相源。
- [ ] 在前端构建或 CI 中生成 API 类型，例如使用 `openapi-typescript`。
- [ ] 将手写 API DTO 与领域 UI Model 分离。
- [ ] 对需要 UI 适配的枚举使用 exhaustive switch，新增类型时 TypeScript 必须编译失败，而不是进入默认分支。
- [ ] CI 对比生成结果，禁止后端契约变化后未更新前端。

**建议目录**

```text
frontend/src/api/generated.ts
frontend/src/api/adapters/
frontend/src/domain/
```

**验收标准**

- 删除手写的 OutboxJobType 和 WritebackTarget 后，前端仍可从生成类型编译。
- 后端新增一个枚举值而前端没有 UI 处理时，CI 明确失败。
- 不再用正则测试证明前后端契约一致。

### P1-02：补齐 CLP 和 Narrative Writeback 前端支持

**整改任务**

- [ ] Post-Acceptance 面板显示 `clp_extraction`。
- [ ] CLP 失败时展示错误、attempt count 和 Retry。
- [ ] `narrative_relation` 提案展示 source、relation、target、有效区间、置信度和 evidence。
- [ ] `story_thread_status` 提案展示当前状态、建议状态和证据。
- [ ] StoryThread 提案的冲突判断基于 StoryThread 当前状态，不再到 CanonEntity 列表查找。
- [ ] 接受 Narrative 提案后刷新 StoryThread、Narrative Graph 和 Director 状态。
- [ ] 未知 WritebackTarget 必须显示“不支持的提案类型”，并禁止接受，不能错误地按 Memory 处理。

**主要涉及文件**

- `frontend/src/types/index.ts`（在生成类型落地后逐步删除 API 类型）
- `frontend/src/stores/reviews.ts`
- `frontend/src/components/manuscript/WritebackReview.vue`
- `frontend/src/components/manuscript/RevisionHistory.vue`
- 新增 Narrative Store 和组件

**验收标准**

- CLP StoryThread 生命周期提案可以在浏览器中接受。
- 接受后后端 StoryThread 状态变化，前端立即显示新状态。
- NarrativeRelation 提案接受后可在 Graph/Director 页面观察。
- 不再存在因目标不是 CanonEntity 而永久禁用 Accept 的情况。

### P1-03：完善异步任务加载、轮询和历史恢复

**问题**

接受正文后前端只加载一次任务状态；重新进入项目时不加载 Outbox；任务数组为空时整个面板连 Refresh 入口一起隐藏。

**整改任务**

- [ ] 项目加载时请求最近的项目 Outbox 任务。
- [ ] 有 `pending` 或 `processing` 时自动轮询。
- [ ] 全部进入 `succeeded` 或 `failed` 后停止轮询。
- [ ] 项目切换、页面卸载和请求取消时停止旧项目轮询。
- [ ] 面板在任务为空时仍保留“加载任务”入口和空状态。
- [ ] 按 revision / aggregate 显示任务组，避免全部历史任务平铺。
- [ ] 后端增加任务类型、aggregate、状态、limit/cursor 查询参数。
- [ ] 默认只加载最近任务，提供查看历史入口。

**验收标准**

- 接受正文后，无需手动 Refresh，状态最终自动变为 succeeded 或 failed。
- 关闭页面后重新打开，失败任务仍可见并可重试。
- 快速切换项目不会把 A 项目的任务写入 B 项目的 Store。
- 长期项目不会一次返回无限增长的全部任务。

### P1-04：Retry API 只负责重新入队

**问题**

当前 Retry HTTP 请求会同步执行完整 Job Handler。CLP 或外部 Wiki 超时会让请求长时间阻塞，并绕过后台 Dispatcher 的统一执行模型。

**整改任务**

- [ ] Retry 只执行 `failed -> pending` 的 compare-and-set。
- [ ] Retry 成功后调用 best-effort dispatcher wake。
- [ ] API 返回 `202 Accepted` 或 pending OutboxJob。
- [ ] Handler 仅由 Dispatcher 执行。
- [ ] 并发 Retry 仍保证只有一个调用成功重新入队。
- [ ] UI 在 Retry 后进入轮询，不等待同步执行结果。

**验收标准**

- 模拟 8 秒 CLP 调用，Retry API 能快速返回。
- 两个并发 Retry 不会执行两次 Handler。
- 应用重启后 pending job 会被 startup sweep 恢复执行。

## 8. Phase 1B：代码质量专项整改

### P1-05：消除前端 Store 循环依赖

**当前依赖问题**

```text
workspace → manuscript → reviews → workspace
manuscript ↔ reviews
snowflake → manuscript / reviews / graph / workspace
```

延迟调用只能缓解初始化和类型推导问题，不能解决职责耦合。

**目标架构**

```text
Vue Components
      ↓
Application Use Cases / Coordinators
      ↓
Domain Stores
      ↓
Typed API Client
```

**整改任务**

- [ ] 新建应用用例层，承载跨领域编排：
  - `switchProject`
  - `acceptManuscriptProposal`
  - `commitManuscriptRevision`
  - `applyWriteback`
  - `refreshPostCommitState`
- [ ] Domain Store 方法显式接收 `projectId`，不通过 `useWorkspaceStore()` 反向读取。
- [ ] `manuscriptStore` 不再 import `reviewsStore`。
- [ ] `reviewsStore` 不再 import `manuscriptStore`、`canonStore`、`memoryStore`、`graphStore`。
- [ ] `workspaceStore` 只管理选中项目、区域、步骤和顶层加载状态。
- [ ] 使用依赖检查工具阻止重新引入 Store 循环依赖。

**验收标准**

- Store 依赖图无环。
- 一个跨领域动作只有一个应用用例入口。
- 项目切换不再在一个 Watcher 中手工维护十余个领域响应和赋值。
- 应用用例可以在无 Vue 组件环境下测试。

### P1-06：拆分超大模块，恢复高内聚

**当前重点文件**

| 文件 | 当前规模 | 建议拆分方向 |
|---|---:|---|
| `frontend/src/stores/manuscript.ts` | 1083 行 | chapters、sceneContracts、proposals、editor、revisions |
| `frontend/src/stores/reviews.ts` | 675 行 | references、writebacks、consistency、analysisJobs |
| `backend/app/models.py` | 751 行 | projects、canon、narrative、manuscript、review、analysis |
| `backend/app/data/sqlite_store.py` | 792 行 | 保留兼容门面，新代码依赖小型 Repository Port |

**前端建议结构**

```text
frontend/src/stores/
  chapters.ts
  sceneContracts.ts
  manuscriptProposals.ts
  manuscriptEditor.ts
  revisions.ts
  references.ts
  writebacks.ts
  analysisJobs.ts
```

**后端建议结构**

```text
backend/app/models/
  project.py
  snowflake.py
  canon.py
  narrative.py
  manuscript.py
  review.py
  analysis.py
  graph.py
```

**整改原则**

- 以业务不变量和生命周期拆分，不按“文件太长”机械切割。
- 兼容导出可以在 `models/__init__.py` 保留，减少一次性修改范围。
- 每次只拆一个边界，并保持测试全绿。
- 不在同一个 PR 中同时重写业务流程和大规模重命名。

**验收标准**

- 领域模块职责可以用一句话说明。
- Store 不同时承担表单草稿、API、跨领域刷新、工作流编排和 UI 状态。
- 新增 Narrative DTO 不再需要编辑总模型文件。
- 核心业务文件原则上控制在约 300–400 行；超过时需证明仍然高内聚。

### P1-07：清理后端分层泄漏和反向依赖

**当前问题**

- Application Service 直接 import `Depends`、`HTTPException` 和 HTTP status。
- `integrations/provider_registry.py` 反向 import `services/compile_service.py`。
- 部分 Service 同时承担业务错误定义和 HTTP 映射。

**目标分层**

```text
routers/http adapters
    ↓
application services
    ↓
domain policies + ports
    ↓
repositories / integrations
```

**整改任务**

- [ ] 定义应用错误：`ProjectNotFoundError`、`SceneNotFoundError`、`ConflictError` 等。
- [ ] Service 只抛应用错误，不抛 `HTTPException`。
- [ ] Router 统一把应用错误映射成 404、409、422、502 等。
- [ ] 将 `build_scene_draft` 等纯业务函数移出 FastAPI Service 模块。
- [ ] Integration 不得 import Router 或 Service。
- [ ] FastAPI `Depends` 只存在于 wiring / router 边缘。
- [ ] 增加 import boundary 测试。

**验收标准**

- `backend/app/services` 中无 FastAPI import。
- `backend/app/integrations` 中无 `app.services` import。
- Service 可以由普通 Python 代码直接实例化调用。
- HTTP 错误映射集中且一致。

### P1-08：统一 Python 依赖管理

**问题**

运行时依赖在 `requirements.txt`，`pyproject.toml` 只声明 Ruff，`uv.lock` 不包含实际应用依赖。标准 `uv sync` 无法构造可运行后端。

**整改任务**

- [ ] 把 FastAPI、Uvicorn、Pydantic、OpenAI、HTTPX、NetworkX 放入 `[project].dependencies`。
- [ ] 把 Ruff 和测试工具放入 dev group / optional dependency。
- [ ] 重新生成 `uv.lock`。
- [ ] 如保留 `requirements.txt`，由锁文件自动导出，不再手工维护。
- [ ] CI 和 README 使用同一套安装命令。
- [ ] 增加干净环境 smoke test。

**目标命令**

```bash
cd backend
uv sync --frozen --extra dev
uv run python -m compileall app
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
```

**验收标准**

- 删除现有 `.venv` 后仅运行上述命令即可完成后端验证。
- 不依赖用户级 site-packages。
- `networkx` 等运行时依赖不会因安装入口不同而缺失。

### P1-09：减少重复编排和重复刷新

**当前重复流程**

正文 Proposal 接受、手工编辑和 Revision Restore 都重复执行：

```text
刷新 manuscript scenes
刷新 revisions
刷新 writebacks
加载 outbox jobs
加载 consistency report
检查 active project 是否变化
```

**整改任务**

- [ ] 建立统一 `refreshCommittedRevisionState(projectId, revisionId)` 应用用例。
- [ ] 服务端正式提交响应返回 scene、revision 和 scheduled job ids，减少立即回读。
- [ ] 前端只在必要时批量刷新相关集合。
- [ ] 把 active-project stale guard 封装为统一请求作用域，而不是每个 action 手工复制。

**验收标准**

- 三条正式 Revision 路径复用同一个前端应用用例。
- 删除重复的 `Promise.all + isActiveProject` 代码块。
- 接受正文后的网络请求数量可预测并有测试覆盖。

### P1-10：替换源码正则测试为行为测试

**问题**

当前前端测试主要通过读取源码并匹配字符串，不能证明 Store 或组件真正工作，还可能把过时契约固定为正确结果。

**整改任务**

- [ ] 引入 Vitest 和 Vue Test Utils。
- [ ] 增加 Pinia Store 行为测试。
- [ ] 增加组件交互测试。
- [ ] 源码正则测试只保留少量架构边界检查。
- [ ] OpenAPI 生成与编译替代手写类型正则断言。

**必须覆盖的前端行为**

- [ ] StoryThread 提案可接受，状态冲突时禁用。
- [ ] CLP failed job 显示 Retry。
- [ ] Retry 后 pending/processing 自动轮询至终态。
- [ ] 项目切换取消旧请求和旧轮询。
- [ ] AI Proposal 编辑后再接受。
- [ ] Copilot Apply 修改草稿但不直接提交权威状态。
- [ ] 页面重开后历史失败任务可见。

### P1-11：扩大静态质量门禁

**整改任务**

- [ ] 先修复当前 13 个 Ruff format 文件。
- [ ] Ruff 分阶段增加 `I`、`UP`、`B`、`SIM`、`C4`、`RUF` 中的高价值规则。
- [ ] 增加 Python 类型检查，例如 Pyright。
- [ ] 增加前端循环依赖检查。
- [ ] 增加 OpenAPI 契约漂移检查。
- [ ] 增加 `git diff --check` 和生成文件一致性检查。

**原则**

不要一次开启全部规则并做无关的大面积格式重写。每批规则应有独立 PR、明确基线和无业务行为变化证明。

## 9. Phase 1C：测试与 CI 恢复

### P1-12：修复 Full Review Loop E2E 竞态

**整改任务**

- [ ] `refreshPanelUntil` 在后端条件满足后再执行一次最终 UI Refresh，或改为直接等待 UI Store 自动轮询。
- [ ] 四类正文任务都进入断言范围，包括 `clp_extraction`。
- [ ] 不用“至少存在 3 个任务”作为完成条件。
- [ ] 根据 aggregate/revision 筛选本次提交对应任务。
- [ ] 断言所有目标任务进入终态后再检查 UI。

### P1-13：修复 Wiki Failure E2E 竞态

**整改任务**

- [ ] 等待目标任务进入 `failed`，不能只等待任务数量。
- [ ] 不使用 `Object.fromEntries(job_type)` 丢弃同类型的多个任务。
- [ ] 按 aggregate id 和 job type 唯一定位任务。
- [ ] Retry 改为异步入队后，测试轮询到 succeeded。
- [ ] 验证重试不会生成重复 Manuscript Revision 或重复 Writeback Proposal。

### P1-14：CI 完成标准

以下 Job 必须全部为 required：

- Backend compileall、lint、format、unit tests。
- Frontend lint、unit/store/component tests、build。
- Real backend Browser E2E。
- Repository hygiene。
- OpenAPI generated type consistency。
- Import/circular dependency boundaries。

**稳定性要求**

- 两条浏览器 E2E 在本地连续运行 3 次通过。
- Linux CI 连续运行 3 次通过。
- 不使用扩大固定 sleep 的方式掩盖竞态。

## 10. Phase 2：作者工作台和产品闭环

### P2-01：改造为真正的三栏作者工作台

**PRD 目标**

```text
左侧：作品 / 卷 / 章 / 场景树
中间：正文或草稿编辑器
右侧：Copilot、Canon、场景约束、角色状态
底部：Consistency、StoryThread、Writeback Review
```

**整改任务**

- [ ] 将当前两栏 Shell 改为可调整宽度的三栏布局。
- [ ] 左侧统一项目、章、Scene 导航，不把章和 Scene 编辑表单混在正文主区域。
- [ ] 中央区域始终保留一个明确的当前写作对象。
- [ ] 右侧面板按上下文显示 Copilot、Canon、Memory、Scene Contract。
- [ ] Review 面板可折叠，不再把六个大型模块纵向堆叠在同一页面。
- [ ] 支持键盘导航和窄屏降级。

### P2-02：AI 草稿先编辑，再进入正式 Manuscript

**目标流程**

```text
生成 Proposal
→ 放入可编辑 Draft Buffer
→ 作者修改
→ 保存并分析
→ 创建正式 Revision
→ 自动派生任务
```

**整改任务**

- [ ] Proposal 内容支持编辑或“复制到草稿”。
- [ ] Proposal 原始内容仍保持不可变，作者修改保存为独立 Draft。
- [ ] 正式 Accept/Commit 使用作者确认后的内容。
- [ ] 未保存草稿继续使用现有 Draft Safety 机制。
- [ ] 显示 AI 原稿与作者修改 diff。

**验收标准**

- 作者不需要先把未经修改的 AI 原稿提交为 v1。
- 一次保存只产生一个正式 Revision。
- Proposal、Draft 和正式 Revision 的来源关系可追踪。

### P2-03：Copilot 支持正文选区和 Apply

**整改任务**

- [ ] 编辑器提供当前选区、光标上下文和 Scene Contract 信息。
- [ ] Copilot 请求自动携带上下文，不再要求手工填写 Scene ID。
- [ ] 建议可以返回多个结构化选项。
- [ ] Apply 只修改 Draft Buffer，不直接写正式 Manuscript。
- [ ] Apply 生成可撤销 patch，并显示 before/after。
- [ ] 接受 Reference Suggestion 状态与“已应用到草稿”状态分离。

**验收标准**

- 用户选择一段正文请求“增加冲突”，获得多个选项。
- 选择一个选项后，中央草稿发生可撤销变化。
- 未点击保存前，数据库正式 Revision 不变化。

### P2-04：统一“保存并分析”入口

**整改任务**

- [ ] 中央编辑器提供明确的“保存版本”和“保存并分析”。
- [ ] 正式 Revision 和四类 Outbox Job 在同一事务创建。
- [ ] UI 自动显示任务进度和 Review 结果。
- [ ] 一致性问题定位到正文证据位置。
- [ ] Writeback 提案可从底部 Review 面板处理。
- [ ] 拒绝提案后可跳回正文问题位置。

### P2-05：暴露 Narrative OS 领域能力

**整改任务**

- [ ] StoryFact 编辑和按 Scene 时间查询。
- [ ] Reader / Character Knowledge 状态查看。
- [ ] StoryThread 创建、生命周期和事件时间线。
- [ ] NarrativeRelation 查看与 Review。
- [ ] Director 报告展示逾期伏笔、提前回收、长期失焦等风险。
- [ ] Graph 页面逐步切换到新的 Narrative Graph/Director 能力，同时保留 advisory 语义。

**原则**

前端不能提供绕过 Review 直接接受 CLP candidate 的隐藏写入口。所有自动提取结果仍必须经过 Writeback Proposal。

### P2-06：PRD 三条核心场景 E2E

#### 场景 A：结构化起草

```text
创建项目
→ 新建 Chapter 和 Scene Contract
→ 生成草稿
→ 编辑草稿
→ 保存为正式 Revision
→ 重新打开项目仍可读取
```

#### 场景 B：Copilot 辅助

```text
选中正文
→ 请求增加冲突
→ 获得多个建议
→ Apply 一个建议
→ Undo / Redo
→ 保存后产生新 Revision
```

#### 场景 C：保存与写回

```text
保存并分析
→ Consistency / Writeback / CLP 任务自动完成
→ 查看证据
→ 接受 Canon、Relation 或 StoryThread 提案
→ 权威状态更新
→ 重新生成 Scene Snapshot 使用新状态
```

## 11. Phase 3：长篇规模化与运维

### P3-01：分页和增量加载

- Outbox、Revision、Writeback、Reference、StoryFact、StoryThread 使用 cursor pagination。
- 项目切换只加载当前工作区需要的数据。
- 正文和版本历史按 Chapter / Scene 延迟加载。
- 大列表使用虚拟滚动。

### P3-02：性能预算

建议建立以下本地性能目标：

| 操作 | 建议目标 |
|---|---:|
| 打开普通项目 | 1 秒内显示可交互框架 |
| 切换 Scene | 300 ms 内显示缓存内容 |
| 保存本地 Revision | 500 ms 内提交权威事务 |
| Outbox 状态可见 | 2 秒内从 pending 更新 |
| 10,000 条历史任务查询 | 分页响应 300 ms 内 |

### P3-03：可观测性

- Outbox Dashboard 显示 job type、aggregate、attempt、duration 和最后错误。
- 记录数据库迁移、备份、恢复和补偿回滚事件。
- 增加健康检查：数据库可写、Dispatcher 运行、可选 CLP 配置状态。
- 日志继续禁止输出 API Key、完整正文和敏感作品内容。

## 12. 测试策略

### 12.1 后端单元与集成测试

必须覆盖：

- Repository CRUD 和约束。
- UnitOfWork rollback。
- Review 状态机和并发冲突。
- Outbox claim、retry、lease recovery 和幂等。
- Narrative Snapshot 时间与知识隔离。
- Backup v2 全量 round-trip。
- Backup 故障注入和补偿回滚。
- OpenAPI 枚举契约。

### 12.2 前端测试

分为三层：

1. 纯函数和领域适配器测试。
2. Pinia Store / Application Use Case 行为测试。
3. Vue 组件交互测试。

源码文本断言只能用于以下少量场景：

- 组件边界防回退。
- 禁止层级 import。
- 禁止巨型 Store 重新吸收已拆分职责。

### 12.3 真实浏览器 E2E

- 使用真实 FastAPI、临时 SQLite Root 和真实 Vite。
- Provider、CLP、Graph 外部部分使用应用自有测试替身，不需要真实 API Key。
- 不 route mock 核心 `/api` 请求。
- 所有异步断言等待业务终态，不依赖固定 sleep。

### 12.4 目标验证命令

```bash
# Backend
cd backend
uv sync --frozen --extra dev
uv run python -m compileall app
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v

# Frontend
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm test
pnpm build
pnpm test:e2e
```

## 13. PR 拆分建议

禁止以一个超大 PR 同时完成全部整改。建议按以下顺序提交：

| PR | 内容 | 必须包含的验证 |
|---|---|---|
| PR-01 | 备份表完整性和 v2 Manifest | 全量 Narrative round-trip |
| PR-02 | 导入预校验和路径安全 | 恶意包不产生任何写入 |
| PR-03 | 数据库 / 文件补偿回滚 | 多故障点注入测试 |
| PR-04 | OpenAPI 生成前端类型 | 契约漂移 CI |
| PR-05 | CLP Outbox 和 Narrative Writeback UI | Store + 组件测试 |
| PR-06 | Outbox 自动轮询和异步 Retry | Dispatcher 和浏览器测试 |
| PR-07 | 前端应用用例层，解除 Store 环 | 依赖图无环 |
| PR-08 | 拆分 Manuscript / Reviews Store | 行为无回退 |
| PR-09 | 后端 Service 与 HTTP 解耦 | import boundary 测试 |
| PR-10 | Python 依赖单一来源 | 干净环境验证 |
| PR-11 | E2E 竞态与 CI 修复 | 连续三次通过 |
| PR-12+ | 三栏工作台和可编辑草稿 | PRD 垂直场景 E2E |

每个 PR 应满足：

- 只解决一个明确问题或一个紧密内聚的工作流。
- 提交前后业务行为变化有说明。
- 新不变量有自动化测试。
- 不夹带无关重命名或格式化。
- 数据迁移和备份格式变化有回滚说明。

## 14. 风险与回滚

### 14.1 备份格式升级风险

旧 v1 包无法补回当时未导出的 Narrative 数据。系统只能明确告知风险，不能伪造完整恢复。v1 覆盖已有项目必须默认禁止。

### 14.2 前端架构拆分风险

Store 拆分期间容易产生状态重复和监听器双执行。应先增加行为测试，再逐个迁移用例；旧 Store 在迁移完成前作为 Facade，不一次性删除。

### 14.3 API 类型生成风险

生成类型可能暴露现有后端模型中的过宽 `dict`。应先接受真实契约，再逐步把关键 Payload 建模为强类型，不能为了让生成结果好看而在前端继续手写另一套类型。

### 14.4 Outbox Retry 改造风险

从同步 Retry 改为异步入队会改变 HTTP 返回语义。前端、E2E 和文档必须在同一个交付批次更新。

## 15. 最终 Definition of Done

项目只有在同时满足以下条件时，才可标记为“可发布本地 MVP”：

### 数据和业务

- [ ] Backup v2 覆盖所有权威项目数据。
- [ ] 任何导入失败都不会改变原项目。
- [ ] CLP、Consistency、Wiki、Writeback 四类任务可观察和可重试。
- [ ] Canon、Memory、NarrativeRelation、StoryThread 提案均可正确 Review。
- [ ] AI 草稿可编辑后再正式提交。
- [ ] Copilot 建议可以安全应用到草稿。

### 代码质量

- [ ] 前端 Domain Store 依赖图无环。
- [ ] Application Service 不依赖 FastAPI。
- [ ] Integration 不反向依赖 Service。
- [ ] Python 依赖有单一真相源。
- [ ] 核心超大模块已按领域拆分。
- [ ] OpenAPI 契约自动生成并受 CI 保护。

### 测试和交付

- [ ] Ruff check 和 format 全绿。
- [ ] 后端完整测试全绿。
- [ ] 前端真实行为测试全绿。
- [ ] 两条现有 E2E 修复并稳定通过。
- [ ] PRD 场景 A、B、C 均有真实浏览器 E2E。
- [ ] CI 所有 Job 为 required 且连续稳定通过。

### 产品体验

- [ ] 第一屏是可持续写作的作者工作台，而非纵向管理表单集合。
- [ ] 当前 Chapter、Scene、Draft、Canon 约束和 Review 状态始终清晰。
- [ ] 用户无需理解 Outbox、CLP 或内部模块边界，也能完成写作和审阅闭环。

## 16. 首批执行清单

建议下一轮开发立即按以下顺序开始：

1. [ ] 暂时禁用覆盖导入。
2. [ ] 为备份补齐六张 Narrative Domain 表。
3. [ ] 增加全量 round-trip 和失败不变性测试。
4. [ ] 将导入所有校验移动到写事务之前。
5. [ ] 实现临时目录和补偿回滚。
6. [ ] 修复 Ruff format 的 13 个文件。
7. [ ] 建立 OpenAPI 前端类型生成。
8. [ ] 补齐 `clp_extraction`、`narrative_relation`、`story_thread_status` UI。
9. [ ] 项目加载时恢复 Outbox，增加自动轮询。
10. [ ] 修复两条真实浏览器 E2E。
11. [ ] 建立前端 Application Use Case 层，开始解除 Store 循环依赖。
12. [ ] 在上述门禁全绿后，再启动三栏工作台和可编辑草稿改造。

---

本计划是针对 `integration-graphify-clp@42dd63f` 的审查整改基线。后续每完成一个阶段，应在本文件中更新任务状态、实际验证结果和偏离原因，避免整改计划与代码再次发生漂移。
