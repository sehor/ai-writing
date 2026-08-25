# AI Writing Studio 改进实施计划

> 适用项目：`E:\projects\ai-writing`  
> 目标：将当前功能较完整但可靠性不足的本地 MVP，提升为数据安全、业务闭环清晰、可持续扩展的本地优先长篇写作工具。

---

## 一、总体实施顺序

```text
恢复稳定基线
→ 解决数据丢失与跨存储一致性
→ 完善审阅和 Write-back 状态机
→ 补齐 Snowflake 到正文、正文到 Canon 的业务闭环
→ 拆分架构热点
→ 建立真实端到端测试和发布门禁
```

---

## 二、改进目标

### 1. 工程目标

1. 所有测试持续通过，禁止带失败测试继续叠加功能。
2. 核心数据保存与外围知识索引解耦，避免“接口报错但数据已经保存”。
3. Router 不再知道 DeepSeek、Hermes 或其他具体供应商。
4. 将 2000+ 行前端 Store 和巨型 DataStore 拆成可独立维护的业务模块。
5. 建立正式数据库迁移、CI、Lint 和真实后端浏览器测试。

### 2. 业务目标

1. AI 只能产生 Proposal，不能直接修改最终项目状态。
2. 所有审核对象都使用一致且不可逆的状态机。
3. Write-back 不仅能创建 Canon，还能更新已有 Canon 状态。
4. Snowflake Step 7、8 能编译为结构化 Canon 和 Scene Proposal。
5. 正文接受后，系统能够产生带证据的一致性报告和状态变化建议。
6. 编辑中的正文、Artifact 和表单不会因切换项目、步骤或页面而静默丢失。

---

## 三、实施原则

### 1. 先稳定，后重构，再扩展

在 P0 问题全部关闭前，暂停新增：

- 新模型供应商
- 更复杂的 GraphRAG
- 新 Agent 类型
- 高级图可视化
- 云同步
- 多人协作

### 2. 一个改动只解决一个问题

不要在同一个提交中同时进行：

- 数据层重构
- 新业务功能
- UI 改版
- 数据库迁移
- 测试框架更换

### 3. 核心状态与派生状态分离

| 类型 | 示例 | 可靠性要求 |
|---|---|---|
| 核心状态 | Project、Canon、Scene、Manuscript、Revision、审核结果 | 必须事务化保存 |
| 派生状态 | LLM Wiki、Graph、搜索索引、模型摘要 | 可以失败、可以重建、必须可重试 |
| 临时状态 | 未保存表单、生成中的响应、编辑草稿 | 必须防止静默丢失 |

---

# 四、阶段一：恢复稳定基线

## P0-01 修复当前失败测试

修改：

```text
backend/app/routers/scenes.py
```

将：

```python
status.HTTP_422_UNPROCESSABLE_CONTENT
```

改为：

```python
status.HTTP_422_UNPROCESSABLE_ENTITY
```

### 验收标准

```text
python -m compileall backend/app
backend unittest 全部通过
frontend pnpm test 通过
frontend pnpm build 通过
browser smoke 通过
```

---

## P0-02 整理当前未提交工作树

建议先形成一个独立提交，范围只包括：

- 跨项目 ID 唯一性
- Scene Chapter 所属项目校验
- Write-back 状态不可逆
- Write-back 接受事务原子性
- 项目切换异步响应隔离
- 对应回归测试

推荐提交说明：

```text
Harden project-scoped data integrity and review transitions
```

---

## P0-03 建立最低 CI 门禁

新增持续集成，至少包含：

### Backend

```text
- Python compileall
- unittest
- ruff check
- ruff format --check
```

### Frontend

```text
- pnpm install --frozen-lockfile
- pnpm test
- pnpm build
```

### Repository

```text
- git diff --check
```

建议新增：

```text
.github/workflows/verify.yml
backend/pyproject.toml
frontend/eslint.config.js
```

---

# 五、阶段二：优先解决数据安全

## P0-04 为 LLM Wiki 写入增加 Outbox

当前问题：

```text
保存 SQLite
→ 再写 LLM Wiki
→ LLM Wiki 失败
→ API 报错
→ SQLite 已经改变
```

应改为：

```text
同一个 SQLite 事务：
1. 保存核心数据
2. 创建 Revision
3. 写入 outbox_jobs

事务提交后：
4. 执行 LLM Wiki ingest
5. 成功标记 succeeded
6. 失败标记 failed，允许重试
```

建议新增表：

```sql
CREATE TABLE outbox_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT ''
);
```

推荐状态：

```text
pending
processing
succeeded
failed
```

建议新增模块：

```text
backend/app/outbox/models.py
backend/app/outbox/service.py
backend/app/outbox/handlers.py
backend/app/data/mixins/outbox.py
```

需要改造：

```text
backend/app/services/manuscript_service.py
backend/app/routers/snowflake.py
```

### 验收测试

```text
给定 LLM Wiki ingest 抛出异常
当用户保存正文
那么：
- 正文版本已正确保存
- Revision 已正确保存
- Outbox Job 为 failed
- API 明确返回“核心数据已保存，索引失败”
- 重试后 Job 变为 succeeded
- 不产生重复 Revision
```

---

## P0-05 增加防丢稿机制

需要覆盖：

- Snowflake Artifact 编辑
- Canon 表单
- Chapter 表单
- Scene Contract 表单
- Memory 表单
- Manuscript 正文编辑
- Reference 请求表单

建议统一草稿模型：

```ts
type EditorDraftState = {
  scopeKey: string
  dirty: boolean
  lastSavedAt?: string
  lastAutosavedAt?: string
}
```

`scopeKey` 示例：

```text
snowflake:{projectId}:{stepNumber}
canon:{projectId}:{entityId|new}
scene:{projectId}:{sceneId|new}
manuscript:{projectId}:{sceneId}
```

建议新增：

```text
frontend/src/composables/useDirtyGuard.ts
frontend/src/services/draftCache.ts
frontend/src/stores/editorSession.ts
```

### 行为要求

用户切换以下对象时：

- 项目
- Snowflake Step
- Chapter
- Scene
- Canon Entity
- Memory Record
- 页面关闭

若存在未保存内容，应：

1. 自动保存本地草稿
2. 显示离开确认
3. 允许取消切换
4. 重新进入时恢复本地草稿

---

## P0-06 完善异步请求隔离

建议实现统一请求作用域：

```ts
type RequestScope = {
  projectId: string
  domain: string
  entityId: string
  requestId: number
}
```

响应写入状态前必须验证：

```ts
isCurrentRequest(scope)
isCurrentProject(scope.projectId)
isCurrentEntity(scope.domain, scope.entityId)
```

例如 Snowflake 生成绑定：

```text
projectId + stepNumber + requestId
```

建议封装：

```text
frontend/src/composables/useScopedRequest.ts
```

### 验收测试

```text
Step 1 开始生成
切换到 Step 2
Step 1 后返回
Step 2 编辑器内容不被覆盖
Step 1 结果仍正确保存到 Step 1 数据中
```

---

# 六、阶段三：统一审阅状态机

## P1-01 建立统一状态迁移规则

建议统一状态：

```text
pending_review
accepted
rejected
superseded
```

合法迁移：

```text
pending_review -> accepted
pending_review -> rejected
pending_review -> superseded
```

禁止：

```text
accepted -> rejected
rejected -> accepted
accepted -> pending_review
```

建议新增：

```text
backend/app/review/state_machine.py
backend/app/review/service.py
```

统一 HTTP 语义：

```text
404：不存在
409：已审核，不允许再次修改
422：请求结构错误
```

---

## P1-02 Write-back 支持更新已有 Canon

扩展：

```python
WritebackAction = Literal["create", "update"]
```

建议 Update Proposal：

```json
{
  "target": "canon_entity",
  "action": "update",
  "target_record_id": "character-lin-ye",
  "expected_version": 3,
  "title": "Update Lin Ye injury state",
  "rationale": "The accepted revision establishes a right-arm injury.",
  "source_ref": "manuscript_revision:revision-24",
  "changes": {
    "current_state": {
      "before": "Uninjured",
      "after": "Right arm injured"
    }
  }
}
```

Canon 增加：

```text
version
updated_at
```

接受 Proposal 时校验：

```text
current_version == expected_version
```

UI 必须展示：

```text
当前值
建议值
变化来源
证据正文
目标记录
冲突警告
```

---

## P1-03 Proposal 入库前完成目标校验

生成 Proposal 时就执行：

```python
validate_writeback_payload(proposal)
```

不要等用户点击接受才发现 Payload 不合法。

Memory 建议：

- 不复制完整 40,000 字符正文
- Prose Sample 建议控制在 2,000–6,000 字符
- Chapter Summary 应存摘要而非正文副本
- 优先保存 source_ref 与选段范围

验收标准：

> 所有已经成功创建的 Write-back Proposal，在数据未发生并发变化时，都应可以被接受。

---

## P1-04 增加分析幂等性

建议新增：

```sql
CREATE TABLE analysis_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    processor TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, source_ref, processor, input_hash)
);
```

Processor 示例：

```text
local_writeback
deepseek_writeback
hermes
consistency_checker
```

重复请求时：

- 输入未改变：返回之前结果
- 用户明确选择重新运行：创建新的 Run Version
- 不静默创建重复 Proposal

---

# 七、阶段四：补齐核心业务闭环

## P1-05 将 Snowflake 从文本框升级为结构化编译器

### Step 7：Canon Proposal

```text
Snowflake Step 7 Artifact
→ Canon Extractor
→ Canon Create / Update Proposals
→ 用户审阅
→ 写入 Canon
```

### Step 8：Scene Contract Proposal

```text
Snowflake Step 8 Artifact
→ Scene Contract Parser
→ 结构校验
→ Scene Proposals
→ 用户批量审阅
→ 创建 Scene Contracts
```

建议 Scene Proposal 包含：

```text
sequence
chapter_id 或 chapter_hint
title
pov
goal
conflict
turning_point
required_canon_ids
forbidden_fact_refs
open_threads
```

设计约束：

- AI 解析失败不能污染数据库
- 原始 Artifact 必须保留
- Proposal 带来源文本和解析警告
- 批量接受必须事务化
- 重复解析必须幂等

---

## P1-06 实现真正的一致性报告

新增结构化模型：

```python
class ConsistencyFinding(BaseModel):
    id: str
    severity: Literal["info", "warning", "critical"]
    rule_code: str
    title: str
    description: str
    manuscript_source_ref: str
    manuscript_excerpt: str
    canon_entity_id: str | None
    canon_field: str | None
    expected_value: str
    observed_value: str
    suggested_action: str
```

首批规则：

1. Forbidden Fact 明文出现
2. Scene POV 与正文角色明显不一致
3. Canon 中声明禁止某能力，正文明确使用
4. `last_seen` 或故事位置明显倒退
5. Required Canon 在正文和上下文中完全缺失
6. Goal / Conflict / Turning Point 没有可识别体现
7. 同一实体状态在相邻 Revision 中冲突

输出应带：

```text
规则代码
证据正文
Canon 来源
置信度
建议动作
```

---

## P1-07 正文接受后自动创建待处理分析

建议核心闭环：

```text
接受 Manuscript Proposal
→ 创建 Revision
→ 创建 Wiki Outbox Job
→ 创建 Consistency Analysis Job
→ 创建 Write-back Analysis Job
→ UI 显示分析状态
→ 分析完成后出现待审阅结果
```

自动的是分析，不是自动接受写回。

---

# 八、阶段五：架构重构

## P2-01 将 Router 恢复为纯 HTTP 层

目标结构：

```text
Router
  -> Application Service
      -> Domain Policy / Workflow
      -> Repository
      -> Integration Port
```

Router 只负责：

- 解析请求
- 调用 Service
- 返回 Response
- 映射领域错误

禁止 Router 直接导入：

```text
DeepSeekSettings
OpenAI SDK
HermesAgentClient
LocalFileLlmWiki
```

建议新增：

```text
backend/app/services/snowflake_service.py
backend/app/services/reference_service.py
backend/app/services/writeback_service.py
backend/app/integrations/provider_registry.py
backend/app/integrations/hermes.py
```

---

## P2-02 建立 Provider Registry

定义：

```python
class WritingProvider(Protocol):
    name: str

    def generate_snowflake(...): ...
    def generate_manuscript(...): ...
    def generate_reference(...): ...
    def generate_writebacks(...): ...
```

注册：

```text
LocalDeterministicProvider
DeepSeekProvider
```

新增 Provider 时只需：

1. 实现接口
2. 注册 Provider
3. 修改配置

---

## P2-03 拆分 `WritingDataStore`

建议拆成：

```python
ProjectRepository
SnowflakeRepository
CanonRepository
SceneRepository
ManuscriptRepository
ReviewRepository
OutboxRepository
AnalysisRepository
```

跨仓储事务通过：

```text
UnitOfWork
```

协调。

---

## P2-04 拆分前端 Store

目标结构：

```text
frontend/src/
  api/
    client.ts
    errors.ts
    projects.ts
    snowflake.ts
    manuscript.ts
    reviews.ts

  stores/
    workspace.ts
    projects.ts
    snowflake.ts
    canon.ts
    manuscript.ts
    reviews.ts
    graph.ts

  composables/
    useScopedRequest.ts
    useDirtyGuard.ts
    useReviewAction.ts

  services/
    draftCache.ts
```

`workspace.ts` 最终只保留：

```text
activeProjectId
activeSection
全局运行状态
跨 Store 协调
```

---

## P2-05 合并两套 LLM Wiki 路径

正式边界建议：

```text
app.llm_wiki.interfaces
app.llm_wiki.local_backend
app.llm_wiki.external_adapter
```

旧的：

```text
app.cognition.llm_wiki
```

处理方式：

- 有价值的 Markdown Exporter 移到 `app.exports.wiki`
- 运行时知识检索保留在 `app.llm_wiki`
- 删除或标记旧模块 deprecated
- 测试迁移到正式实现
- README 只描述一套架构

---

## P2-06 引入正式数据库迁移

建议目录：

```text
backend/app/data/migrations/
  001_initial.sql
  002_add_chapters.sql
  003_add_review_versions.sql
  004_add_outbox.sql
  005_add_analysis_runs.sql
```

新增：

```text
schema_migrations
```

启动时：

1. 读取当前版本
2. 顺序应用迁移
3. 每个迁移使用事务
4. 记录成功版本
5. 失败时停止启动并给出明确错误

必须测试：

```text
空数据库升级
旧数据库升级
迁移重复执行
迁移中途失败回滚
现有 app.db 数据不丢失
```

---

# 九、阶段六：测试和产品可靠性

## P1-08 真实后端浏览器测试

新增真实测试栈：

```text
临时 SQLite
真实 FastAPI
真实 Vite
Playwright 浏览器
Local Deterministic Provider
临时 LLM Wiki 目录
```

首条完整 E2E：

```text
创建项目
→ 保存 Step 7
→ 生成 Canon Proposal
→ 接受 Canon
→ 创建 Chapter
→ 创建 Scene
→ 生成 Manuscript Proposal
→ 接受正文
→ 生成 Revision
→ 运行一致性分析
→ 接受 Write-back Update
→ 验证 Canon 已更新
→ 导出 Markdown
→ 重启后数据仍存在
```

故障 E2E：

```text
LLM Wiki 写入失败
→ 正文仍保存
→ UI 显示索引失败
→ 用户重试
→ 索引成功
→ 不产生重复正文版本
```

---

## P2-07 增加备份和恢复

至少提供：

```text
导出项目包
导入项目包
数据库备份
知识文件备份
版本兼容检查
恢复前预览
```

项目包建议包括：

```text
manifest.json
project.sqlite 或结构化 JSON
manuscript/
canon/
memory/
snowflake/
wiki/
attachments/
```

---

## P2-08 增加运行可观察性

最低限度记录：

```text
request_id
project_id
operation
aggregate_id
provider
duration
result
error_code
```

禁止记录：

```text
API Key
完整正文
完整 Canon 私密内容
完整 Provider Prompt
```

建议诊断页展示：

```text
最近失败的 Outbox Job
最近失败的 Provider 请求
数据库 Schema Version
当前 Provider
知识索引状态
最后备份时间
```

---

# 十、推荐提交顺序

| 顺序 | 内容 | 性质 |
|---:|---|---|
| 1 | 修复 422 常量并恢复全部测试 | Hotfix |
| 2 | 提交当前数据完整性和项目切换修复 | Correctness |
| 3 | 加入 CI、Ruff、ESLint 基础门禁 | Tooling |
| 4 | 引入 Outbox 表和 Repository | Infrastructure |
| 5 | Manuscript 保存接入 Outbox | Vertical slice |
| 6 | Snowflake 保存接入 Outbox | Vertical slice |
| 7 | 前端 Dirty Guard 和本地草稿 | Data safety |
| 8 | 请求 Scope 与取消机制 | Concurrency |
| 9 | 统一 Review State Machine | Domain rule |
| 10 | Write-back Update Canon | Core feature |
| 11 | Proposal 预校验和分析幂等 | Reliability |
| 12 | Step 7 → Canon Proposal | Product loop |
| 13 | Step 8 → Scene Proposal | Product loop |
| 14 | 结构化一致性 Finding | Product loop |
| 15 | 自动分析任务 | Workflow |
| 16 | 拆分 Provider Registry | Architecture |
| 17 | 拆分 Repository 和 Unit of Work | Architecture |
| 18 | 拆分前端 Store | Architecture |
| 19 | 合并 LLM Wiki 实现 | Cleanup |
| 20 | 正式迁移和真实后端 E2E | Release readiness |

---

# 十一、每个改动的完成标准

每个任务必须满足：

```text
1. 有明确行为变化说明
2. 先增加或更新回归测试
3. 后端 compileall 通过
4. 后端全部测试通过
5. 前端测试通过
6. 前端 build 通过
7. 涉及主流程时真实 E2E 通过
8. 数据迁移有升级测试
9. 外部副作用具有幂等性
10. 不引入未说明的 Provider 或大依赖
11. 不留下已知数据安全问题
12. README 和 development-plan 与真实实现同步
```

---

# 十二、最终验收指标

| 指标 | 目标 |
|---|---|
| 后端测试 | 全部通过 |
| 前端测试和构建 | 全部通过 |
| CI | 主分支持续全绿 |
| 核心数据失败语义 | 不再出现“报错但已静默提交” |
| 编辑安全 | 项目、步骤、场景切换不丢稿 |
| 审阅状态 | Accepted / Rejected 不可反向修改 |
| Write-back | 支持 Create 和 Update Canon |
| 分析幂等性 | 同一输入不产生重复 Proposal |
| Snowflake 编译 | Step 7、8 可形成结构化 Proposal |
| 一致性检查 | 输出带证据的结构化 Finding |
| Provider 耦合 | Router 不导入具体 Provider |
| LLM Wiki | 只有一套正式运行边界 |
| 数据库升级 | 有版本化迁移 |
| 浏览器测试 | 使用真实 FastAPI 和临时 SQLite |
| 恢复能力 | 可导出和恢复完整项目 |

---

# 十三、最重要的执行判断

> 先完成“数据安全 + 审阅状态机 + Canon Update Write-back”，再继续扩展 Agent 和模型能力。

这三项决定项目能否从“功能演示”转变为“可信赖的长期写作工具”。

建议执行优先级：

```text
P0：稳定性与数据安全
P1：核心业务闭环
P2：架构和工程化
```
