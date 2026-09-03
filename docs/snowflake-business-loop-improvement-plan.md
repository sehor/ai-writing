# Snowflake Method 业务闭环改进执行计划

- 状态：Implemented；兼容接口的物理删除待人工确认
- 编写日期：2026-09-03
- 设计审查基线：`967bb82`
- 实施提交：`7d601b6`、`af47f26`、`c4aa732`
- 验证基线：后端 263 项测试、前端 31 项 Node 测试和 27 项 Vitest 测试通过；Python compileall、ESLint、前端 build 通过
- 文档关系：本计划是 `docs/ai-writing-improvement-plan.md` 的 Snowflake 专项补充，不替代已有的全局改进路线图

## 0. 实施状态

P0–P5 与 SF-601/SF-602 已完成。SF-603 已完成运行时兼容收口：旧接口标记弃用，`snowflake_artifacts` 只作为 accepted projection 更新，Step 10 旧正文保留为 `legacy_draft`，`open_threads` 不再作为生成依据，未执行的检查不再伪装成 reviewer 成功。

以下项目有意保留，不能视为未完成缺陷：

- 旧 Snowflake generate/artifact PUT 与 Manuscript status-accept 接口继续提供迁移期兼容；
- `open_threads` 字段继续支持历史备份读取，但不参与新生成；
- Step 10 `legacy_draft` 继续只读保留，并只能由作者选段导入为待审核 Manuscript proposal；
- 上述兼容面的物理删除需要项目负责人确认历史备份支持周期和客户端迁移完成情况。

第 4 节记录的是 `967bb82` 时点的历史审查证据，用于解释本计划来源，不代表当前实现状态。

## 1. 目标

把当前“雪花法启发的叙事状态与审阅系统”改造成严格、可追踪、可回改的 Snowflake Method 业务闭环，同时复用项目已经成熟的 Canon、Narrative Snapshot、Manuscript proposal/revision 和 Outbox 能力。

完成后应满足：

1. AI 只创建提案，不能直接覆盖或批准当前 Snowflake 产物。
2. 每个步骤都拥有可追踪的修订历史、上游版本快照和传递式 stale 状态。
3. 十个步骤的输出契约可验证，而不是只依赖提示词中的自然语言描述。
4. 第 8 步产生的场景、开放线索和线程动作能进入结构化 Narrative 数据。
5. 第 10 步直接使用现有的按场景 Manuscript proposal/revision 流程，不再维护第二套大文本正文。
6. 第 6–9 步可支撑长篇项目和上百场景，不受单一 Markdown blob 长度限制。
7. 所有显示为“已检查”的状态都对应真实验证结果。

## 2. 非目标

本计划不包含：

- 替换 FastAPI、Vue、SQLite 或 Pinia。
- 引入 LangChain、LangGraph 或新的大型框架。
- 让 AI 自动决定 Canon、StoryThread 或正文是否生效。
- 重写现有 Manuscript revision、Outbox、Narrative Snapshot 或 post-accept analysis 主链。
- 在结构化契约和审阅状态稳定之前扩展新的模型供应商。

## 3. 假设与推荐决策

以下决策作为本计划的默认前提，实施前应由项目负责人确认：

1. AI 生成结果一律进入 `pending_review`。
2. 人工编辑默认保存为 `draft`；只有显式的 Accept/Approve 操作才更新当前 accepted head。
3. 第 9 步是可选步骤，可以被显式标记为 `skipped`。
4. 第 10 步是虚拟工作流里程碑，其完成度来自 Manuscript 场景修订覆盖率，不再存储新的单篇正文 Artifact。
5. 旧数据只做追加式迁移，不删除、不原地重写作者内容。
6. critical validation finding 默认阻止接受；若允许 override，必须记录人工理由。

## 4. 当前审查结论

总体判断：思想与架构约 `7/10`，十步业务落地约 `5.5/10`。这些分数是用于沟通优先级的主观指标，不是自动化质量度量。

### 4.1 AI 生成直接覆盖并批准规划产物

结论：确认。

当前链路：

```text
POST /snowflake/generate
  -> SnowflakeService.generate
  -> WritingWorkflow/DeepSeekWritingWorkflow
  -> enqueue_snowflake_index_job
  -> SnowflakeRepository.save (UPSERT)
  -> advance_project_current_step
  -> Wiki payload status=approved（第 1–9 步）
```

静态证据：

- `backend/app/agents/deepseek_workflow.py:174-183`：提示词声明 AI 只产生 draft，由人决定是否保存。
- `backend/app/services/snowflake_service.py:195-210`：生成后立即保存并排队索引。
- `backend/app/data/flows.py:62-85`：保存、推进步骤和 Outbox 入队发生在同一事务。
- `backend/app/data/repositories/snowflake.py:46-54`：同一步骤通过 UPSERT 覆盖。
- `backend/app/outbox/handlers.py:43-55`：第 1–9 步作为 `approved` 规划证据。
- `frontend/src/stores/snowflake.ts:133-183`：前端将响应写入已保存 Artifact，并显示 `Draft generated and saved.`。

### 4.2 回改没有形成递归反馈

结论：确认，但存在局部编译运行版本，不构成全局反馈机制。

`SnowflakeArtifact` 和 `snowflake_artifacts` 只有项目、步骤、类型和正文，没有：

- revision/version；
- 当前 accepted head；
- 上游版本或内容哈希；
- `stale/needs_review` 状态；
- 步骤依赖快照。

第 7、8 步的 compiler `analysis_runs` 拥有 fingerprint、run version 和 pending proposal supersede，但只有重新执行 compiler 时才生效，不能在第 2 步变化后自动使第 4、6、8、9、10 步失效。

静态证据：

- `backend/app/models.py:124-128`
- `backend/app/data/migrations.py:32-38`
- `backend/app/services/snowflake_compile_service.py:1-12`
- `frontend/src/components/SnowflakeWorkspace.vue:88-148`

### 4.3 十步名称存在，结构化契约不足

结论：确认。

主要偏差：

- 第 2 步只有 beginning/middle/end 描述，没有 `setup + 三次灾难 + ending` 和因果升级约束。
- 第 3 步没有强制 Motivation、Goal、Conflict、Epiphany、人物视角故事摘要。
- 第 4 步没有将每个段落绑定到第 2 步具体句子或 beat。
- 第 7 步被实现为通用 Canon 世界资料提取，而不是完整 Character Chart/Profile。
- 第 9 步没有 `optional` 元数据和显式 skip 状态。
- DeepSeek 只有第 8、10 步拥有少量附加规则，其他步骤依赖模型自由理解。

第 7 步解析器只识别 `summary/current_state/constraints/last_seen/timeline_notes` 等 Canon 字段。`Goal`、`Motivation`、`Epiphany` 等人物字段会被 `_apply_field` 无提示忽略。

静态证据：

- `backend/app/services/snowflake_service.py:37-97`
- `backend/app/llm_wiki/stage_protocol.py:13-83`
- `backend/app/agents/deepseek_workflow.py:232-261`
- `backend/app/agents/writing_workflow.py:308-328`
- `backend/app/snowflake_compiler/canon_extractor.py:36-78,275-290`

### 4.4 第 8 步和正文系统存在两条路径

结论：核心问题确认，但项目不是完全没有第 8 步到正文的路径。

已经存在的正确路径是：

```text
Step 8 Artifact
  -> Scene Proposal
  -> 人工接受
  -> Scene Contract
  -> Manuscript proposal
  -> 人工接受
  -> ManuscriptRevision
```

问题在于 Snowflake 第 10 步没有接入这条路径。它只读取前序 Snowflake 文本 Artifact、Canon、Memory 和 Wiki context，不读取已接受的 Scene Contract 数据库；生成结果又成为独立的 `manuscript` 文本 Artifact。

此外，第 8 步的 `open_threads` 会写入 Scene Contract，但 Manuscript provider 生成时通过 `scene_for_generation()` 主动清空。实际生成上下文只使用独立的 StoryThread/Event，而当前前端没有从 Step 8 proposal 创建 StoryThread 的闭环。

静态证据：

- `backend/app/agents/writing_workflow.py:105-123`
- `backend/app/services/manuscript_service.py:113-195`
- `backend/app/narrative/snapshot.py:152-170,261-285`
- `frontend/src/stores/narrative.ts:18-41`
- `backend/app/outbox/handlers.py:43-55`

### 4.5 长篇内容受到模型与 API 限制

结论：确认，但需要修正前端机制描述。

现有限制：

- `SnowflakeGenerationRequest.user_input`：4,000 字符；
- `SnowflakeArtifactUpdate.content`：20,000 字符；
- DeepSeek 默认输出：2,400 tokens；
- 每个前序 Snowflake Artifact 进入 DeepSeek context 前截断到 4,000 字符。

前端切换到下一步时会加载下一步自己的草稿或空值，不会自动把上一步完整产物作为 `user_input`。但用户在当前步骤对一个超过 4,000 字符的 Artifact 执行 regenerate 时，整个编辑器内容会被当作 `user_input`，因此仍会失败。

静态证据：

- `backend/app/models.py:98-113`
- `backend/app/agents/deepseek_workflow.py:35-60,264-275`
- `frontend/src/stores/snowflake.ts:133-161`
- `frontend/src/stores/workspace.ts:325-352`

### 4.6 Scene Contract 只有 warning，没有质量门槛

结论：确认。

- POV、Goal、Conflict、Turning Point 在模型中允许为空。
- 解析器仅写 warning。
- 接受事务只检查 proposal 状态、场景序号和章节归属。
- 前端默认选中所有 pending proposal，并提供 Accept All Pending。

静态证据：

- `backend/app/models.py:322-348,675-717`
- `backend/app/snowflake_compiler/scene_parser.py:287-306`
- `backend/app/data/flows.py:390-433`
- `frontend/src/stores/snowflake.ts:203-215`
- `frontend/src/components/SnowflakeWorkspace.vue:274-358`

### 4.7 Snowflake Consistency Reviewer 名不副实

结论：在 Snowflake 生成链中确认，不能泛化为整个项目没有一致性检查。

`LocalConsistencyReviewer` 只写入 `checked against loaded canon` trace，没有产生 finding 或执行比较；DeepSeek workflow 也复用它。另一方面，接受 ManuscriptRevision 后，Outbox 会运行真正的 `analysis.consistency.check_revision`。

因此准确的问题是：

> Snowflake 和 Manuscript proposal 接受前没有真实一致性质量门，已有检查主要发生在正文提交之后。

静态证据：

- `backend/app/agents/writing_workflow.py:197-203`
- `backend/app/agents/deepseek_workflow.py:128-145`
- `backend/app/outbox/handlers.py:112-145`
- `backend/app/analysis/consistency.py:1-22`

## 5. 必须保持的业务不变量

### SF-INV-01 AI 不能直接提交 Snowflake 状态

AI provider 只能返回候选内容。生成成功不能更新 accepted head、推进步骤、写入 approved Wiki 或使下游产物生效。

### SF-INV-02 接受操作是唯一提交点

只有人工 Accept/Approve 可以在一个事务中：

1. 校验预期版本；
2. 更新 accepted head；
3. 推进步骤；
4. 标记下游 stale；
5. 创建 Outbox job。

### SF-INV-03 修订只追加，不覆盖历史

任何 human edit、AI generation、restore 或 import 都创建新 revision。`snowflake_artifacts` 若继续存在，只能作为当前 accepted head 的兼容投影。

### SF-INV-04 stale 不等于删除

上游变化只使下游进入 `needs_review`，不能自动删除、重写或拒绝作者已有内容。

### SF-INV-05 Canon 与规划资料保持边界

Character Profile 可以包含动机、目标、秘密、顿悟和弧线；只有被明确确认为故事事实的字段才能转换成 Canon proposal。

### SF-INV-06 正文只有一条正式提交路径

所有正式正文都必须经过 Manuscript proposal -> human acceptance -> ManuscriptRevision。Snowflake Step 10 不得创建第二种正式正文记录。

### SF-INV-07 trace 必须反映真实执行

没有实际执行检查时只能报告 `skipped/not_run`，不能报告 `checked/passed`。

## 6. 目标领域模型

### 6.1 SnowflakeStepSpec

建立唯一的步骤规格来源，供 service、Wiki stage policy、provider prompt、validator 和前端共同使用。

概念结构：

```python
@dataclass(frozen=True)
class SnowflakeStepSpec:
    number: int
    title: str
    artifact_type: str
    dependencies: tuple[int, ...]
    optional: bool
    schema_version: int
    validator_name: str
```

`backend/app/llm_wiki/stage_protocol.py` 应从这份规格派生 planned source steps，不能继续独立维护另一份步骤依赖表。

### 6.2 SnowflakeArtifactRevision

建议新增追加式表 `snowflake_artifact_revisions`：

| 字段 | 用途 |
| --- | --- |
| `id` | 不可变 revision ID |
| `project_id` | 项目范围 |
| `step_number` | Snowflake 步骤 |
| `artifact_type` | 产物类型 |
| `revision_no` | 步骤内递增版本 |
| `source` | `human`、`ai`、`legacy` |
| `status` | `draft`、`pending_review`、`accepted`、`rejected`、`superseded` |
| `content` | Markdown 投影或短文本正文 |
| `structured_payload` | 经过 schema 验证的 JSON |
| `schema_version` | 输出契约版本 |
| `parent_revision_id` | 修订来源 |
| `base_head_revision_id` | 生成/编辑时看到的 accepted head，用于并发检查 |
| `upstream_snapshot` | 上游 accepted revision ID/hash 映射 |
| `created_at/reviewed_at` | 审计信息 |

建议新增 `snowflake_artifact_heads`：

- 每个 `(project_id, step_number)` 一行；
- 保存 `accepted_revision_id`；
- 保存 `state=missing|approved|stale|skipped`；
- 保存 stale 原因和触发它的上游 revision。

迁移期间保留现有 `snowflake_artifacts` 作为兼容投影，避免一次性破坏现有读取者。

### 6.3 步骤运行状态

前后端统一使用：

```text
missing
draft
pending_review
approved
stale
skipped       # 仅可选步骤
```

`Saved` 不再是完整业务状态。

## 7. API 契约建议

优先新增资源式接口，迁移前端后再废弃旧 `/snowflake/generate` 自动保存语义。

| 接口 | 行为 |
| --- | --- |
| `GET /projects/{project_id}/snowflake/steps` | 返回步骤规格、当前状态、accepted head 和 pending 数量 |
| `GET /projects/{project_id}/snowflake/artifacts/{step}/revisions` | 分页读取修订历史 |
| `POST /projects/{project_id}/snowflake/artifact-revisions` | 创建人工 draft revision |
| `PATCH /projects/{project_id}/snowflake/artifact-revisions/{revision_id}` | 修改尚未结束的 draft/pending revision |
| `POST /projects/{project_id}/snowflake/generations` | 调用 provider，并创建 `pending_review` revision |
| `POST /projects/{project_id}/snowflake/artifact-revisions/{revision_id}/decisions` | 提交 accepted/rejected 决策和预期 head |
| `POST /projects/{project_id}/snowflake/steps/{step}/skip-decisions` | 显式跳过可选步骤 |

接口规则：

- 所有响应使用明确 Pydantic 模型。
- provider 响应视为不可信输入，必须先解析、验证，再创建 revision。
- accepted decision 使用 optimistic concurrency；head 已变化时返回 `409`。
- schema 不合法、依赖未满足或存在 blocking finding 时返回 `422`。
- 生成失败不能留下 accepted Artifact 或 approved Wiki 文档。
- List 接口从一开始支持分页，避免长篇项目再次出现全量加载问题。

## 8. 十步结构化输出契约

### Step 1：One Sentence

必需字段：

- protagonist；
- story goal/problem；
- opposition/stakes；
- one-sentence promise。

### Step 2：One Paragraph

必需字段：

- `setup`；
- `disaster_1`；
- `disaster_2`；
- `disaster_3`；
- `ending`；
- 每个 disaster 的触发原因和主角行动；
- 后两次灾难相对前一次的升级关系。

### Step 3：Character Summary

每个主要人物必需字段：

- name、role；
- one-sentence summary；
- motivation；
- goal；
- conflict；
- epiphany；
- one-paragraph story summary from this character's viewpoint。

### Step 4：One Page Synopsis

- 每一段引用 Step 2 的一个 beat ID。
- 不允许遗漏、合并或新增关键 beat 而不产生 warning。
- 验证 setup、三次灾难和 ending 的覆盖率。

### Step 5：Character Viewpoints

- 每个主要人物独立展开故事视角。
- 显式记录人物知道、不知道和误解的信息。
- 与 Step 3 Character Profile 保持引用关系。

### Step 6：Expanded Synopsis

- 按 act/section/sequence 分块存储。
- 每块关联 Step 4 段落和相关人物。
- 不再要求整个多页大纲保存在一个 20,000 字符字段中。

### Step 7：Character Bible

- 使用独立 Character Profile 记录完整人物图谱。
- 世界、地点、物品、阵营资料可以作为相邻规划记录，但不能取代人物图谱。
- Canon extractor 只把明确标记为 confirmed fact 的内容转换为 Canon proposal。
- 未识别字段必须成为 warning 或 validation error，不能静默忽略。

### Step 8：Scene List

每个 Scene Contract 最低字段：

- POV；
- Goal；
- Conflict；
- Turning Point；
- Outcome/Disaster；
- Required Canon；
- Forbidden Facts；
- Information Delta；
- Character State Delta；
- StoryThread Actions。

### Step 9：Scene Expansion（可选）

- 按 `scene_id` 存储详细 beats、情绪变化和章节计划。
- 允许显式 skip。
- 被跳过时，Step 10 直接使用 Step 8 Scene Contract。

### Step 10：Draft Manuscript

- 不再产生独立 Snowflake Artifact。
- 展示 Scene Contract 到 ManuscriptRevision 的覆盖率。
- 所有生成、编辑、接受、diff、restore 和导出复用现有 Manuscript 服务。

## 9. 分阶段实施计划

依赖顺序：

```text
P0 契约冻结
  -> P1 Revision/Review 主链
  -> P2 依赖与 stale
  -> P3 分步骤 schema 与记录式存储
  -> P4 Scene/StoryThread 与质量门
  -> P5 Step 10/Manuscript 合流
  -> P6 真实一致性检查与兼容清理
```

### P0：冻结业务契约和验证基线

#### SF-001：建立 SnowflakeStepSpec

- 目标：把步骤、依赖、optional 和 schema version 收敛到单一来源。
- 主要文件：
  - `backend/app/services/snowflake_service.py`
  - `backend/app/llm_wiki/stage_protocol.py`
  - 新增 `backend/app/snowflake/step_spec.py`
  - `backend/app/models.py`
- 验收：service、Wiki policy 和前端步骤接口读取同一份定义。
- 验证：步骤 1–10 的契约快照测试；依赖图无环测试。

#### SF-002：修复 Compiler 路由测试的 lifespan 使用

- 目标：让后续路由测试能作为可信质量门。
- 主要文件：
  - `backend/tests/test_snowflake_compiler.py`
  - 如需公共 fixture，新增或修改一个测试辅助文件
- 实施：使用 `with TestClient(app) as client:` 或统一 lifespan-aware fixture，确保 `app.state.outbox_dispatcher` 已初始化。
- 验收：测试不再依赖未进入 lifespan 的全局 app 状态。
- 注意：该任务只修测试装配，不改变生产 dispatcher 语义。

### P1：建立 Revision/Review 主链

#### SF-101：新增 revision/head 数据模型和迁移

- 目标：追加式保存 Snowflake 修订，保留当前 accepted head。
- 主要文件：
  - `backend/app/models.py`
  - `backend/app/data/migrations.py`
  - `backend/app/data/repositories/snowflake.py`
  - `backend/app/data/interfaces.py`
  - `backend/app/data/sqlite_store.py`
- 验收：旧 Artifact 可回填为 revision 1；同一步骤可存在多个修订；历史不可被 UPSERT 覆盖。
- 验证：迁移、回填、revision number、head 查询和回滚测试。

#### SF-102：实现创建、接受和拒绝事务

- 目标：只有 accepted decision 可以更新权威状态。
- 主要文件：
  - `backend/app/data/flows.py`
  - `backend/app/services/snowflake_service.py`
  - `backend/app/routers/snowflake.py`
  - `backend/app/outbox/handlers.py`
  - `backend/app/models.py`
- 验收：Generate 不更新 head/current_step/Wiki；Accept 原子更新这些状态；并发 head 冲突返回 409。
- 验证：service、route、事务回滚和幂等测试。

#### SF-103：前端切换到 revision review

- 目标：编辑器明确区分 draft、pending、accepted 和 stale。
- 主要文件：
  - `frontend/src/types/index.ts`
  - `frontend/src/stores/snowflake.ts`
  - `frontend/src/components/SnowflakeWorkspace.vue`
  - 必要时新增一个 revision review 子组件
- 验收：Generate 后显示待审核；只有 Accept 后步骤显示 Approved；可以查看历史并拒绝提案。
- 验证：Pinia store 测试、组件交互测试和未保存草稿恢复测试。

### P2：实现依赖快照和传递式 stale

#### SF-201：依赖计算与 stale 标记

- 目标：上游 accepted revision 变化后标记所有传递下游。
- 主要文件：
  - `backend/app/snowflake/step_spec.py`
  - 新增 `backend/app/snowflake/dependencies.py`
  - `backend/app/data/repositories/snowflake.py`
  - `backend/app/data/flows.py`
  - `backend/app/services/snowflake_service.py`
- 验收：接受 Step 2 新版本后，Step 4、6、8、9 以及正文 readiness 进入 stale；原内容保留。
- 验证：依赖闭包、无关步骤不失效、重复接受幂等测试。

#### SF-202：前端显示影响范围和 Needs Review

- 目标：作者在接受上游修改前后都能看到影响。
- 主要文件：
  - `frontend/src/types/index.ts`
  - `frontend/src/stores/snowflake.ts`
  - `frontend/src/components/SnowflakeWorkspace.vue`
- 验收：步骤列表不再只显示 Saved；接受前显示将失效的步骤；stale 产物可以查看和重新确认。
- 验证：状态映射和 impact preview 组件测试。

### P3：分步骤 schema 和记录式存储

#### SF-301：实现 Step 1–5 契约与验证器

- 目标：确保早期故事骨架具有明确结构和引用关系。
- 主要文件：
  - 新增 `backend/app/snowflake/contracts.py`
  - 新增 `backend/app/snowflake/validators.py`
  - `backend/app/models.py`
  - `backend/app/agents/deepseek_workflow.py`
  - `backend/app/agents/writing_workflow.py`
- 验收：Step 2/3/4 的关键字段和展开关系可验证；无效 provider 输出只能成为失败结果或带错误的 pending proposal。
- 验证：每一步的 valid/invalid fixture 测试。

#### SF-302：实现 Step 6–9 记录式存储和分页

- 目标：取消多页大纲、人物表和上百场景对单个 blob 的依赖。
- 主要文件：
  - `backend/app/data/migrations.py`
  - 新增或扩展对应 repository
  - `backend/app/data/interfaces.py`
  - `backend/app/data/sqlite_store.py`
  - `backend/app/routers/snowflake.py`
- 验收：记录可以分页、单独修订和局部生成；100+ 场景无需拼接成一个 20,000 字符 Artifact。
- 验证：分页边界、排序、局部 revision 和大项目数据测试。

#### SF-303：重构 provider 生成请求

- 目标：区分“作者指令”和“已有 Artifact 内容”。
- 主要文件：
  - `backend/app/models.py`
  - `backend/app/agents/deepseek_workflow.py`
  - `backend/app/integrations/provider_registry.py`
  - `frontend/src/stores/snowflake.ts`
- 请求应包含：`instruction`、`base_revision_id`、目标 record IDs、generation mode，而不是把完整编辑器内容塞进 4,000 字符 `user_input`。
- 验收：长产物可以按记录或选区继续扩写；prompt 使用相关上游记录，不再固定截断每个 Artifact 后全部拼接。
- 验证：prompt budget、target selection 和 response validation 测试。

#### SF-304：恢复完整 Character Profile 与 Canon 边界

- 目标：第 7 步不再丢失人物字段。
- 主要文件：
  - `backend/app/snowflake_compiler/canon_extractor.py`
  - `backend/app/snowflake/contracts.py`
  - `backend/app/services/snowflake_compile_service.py`
  - `backend/app/models.py`
  - 对应 frontend editor/review 组件
- 验收：Motivation、Goal、Conflict、Epiphany 和人物视角摘要完整保留；Canon 只接收明确事实 proposal；未知字段可见。
- 验证：字段保留、未知字段、Canon proposal 映射测试。

### P4：补齐 Scene Contract、StoryThread 和质量门

#### SF-401：扩展场景契约

- 目标：加入 Outcome/Disaster、Information Delta、Character State Delta 和 Thread Actions。
- 主要文件：
  - `backend/app/models.py`
  - `backend/app/data/migrations.py`
  - `backend/app/data/repositories/scenes.py`
  - `backend/app/snowflake_compiler/scene_parser.py`
  - `backend/app/services/snowflake_compile_service.py`
- 验收：新增字段从生成、解析、proposal 到 Scene Contract 不丢失。
- 验证：解析、数据库 round-trip 和旧 Scene Contract 兼容测试。

#### SF-402：生成可审核的 StoryThread proposal

- 目标：把 Step 8 中的线索转成 Narrative Domain 可接受记录。
- 主要文件：
  - `backend/app/models.py`
  - `backend/app/services/snowflake_compile_service.py`
  - `backend/app/data/flows.py`
  - `backend/app/routers/narrative.py`
  - `backend/app/review/service.py`
- 验收：Step 8 编译可以产生 StoryThread create 和 StoryThreadEvent proposal；接受后正文 snapshot 能读取它们。
- 验证：创建、事件引用、事务回滚和拒绝测试。

#### SF-403：增加 blocking quality gate

- 目标：区分 warning 和 blocking error。
- 主要文件：
  - `backend/app/snowflake_compiler/scene_parser.py`
  - `backend/app/data/flows.py`
  - `backend/app/models.py`
  - `frontend/src/stores/snowflake.ts`
  - `frontend/src/components/SnowflakeWorkspace.vue`
- 验收：核心字段缺失、必需 Canon 未解析或线程引用无效时，服务端拒绝接受；前端不默认勾选这些 proposal。
- 验证：单条、批量、Accept All 和原子回滚测试。

### P5：让 Step 10 汇入 Manuscript

#### SF-501：将 Step 10 改为虚拟 Manuscript 里程碑

- 目标：删除产品层面的第二套正文生成入口。
- 主要文件：
  - `backend/app/services/snowflake_service.py`
  - `backend/app/agents/deepseek_workflow.py`
  - `backend/app/services/manuscript_service.py`
  - `frontend/src/components/SnowflakeWorkspace.vue`
  - 对应 Manuscript workspace 组件
- 验收：Step 10 只能进入现有按场景 proposal/revision 流程；不能再生成 Snowflake manuscript blob。
- 验证：从 Step 8/9 到 Manuscript proposal、接受和 revision 的集成测试。

#### SF-502：迁移旧 Step 10 Artifact

- 目标：保留作者旧正文，避免错误批准。
- 主要文件：
  - `backend/app/data/migrations.py`
  - `backend/app/data/repositories/snowflake.py`
  - `backend/app/services/manuscript_service.py`
  - `backend/app/routers/manuscript.py`
- 默认策略：回填为 `legacy_draft`，只读展示，并提供人工拆分/导入为场景 proposal 的入口。
- 验收：无旧正文丢失；旧内容不会自动成为 ManuscriptRevision 或 approved Wiki evidence。
- 验证：迁移、重复迁移和 legacy import 测试。

#### SF-503：实现 Step 10 完成度

- 目标：按场景覆盖率计算正文阶段状态。
- 完成度至少显示：
  - Scene Contract 总数；
  - 已有 pending manuscript proposal 数；
  - 已有 accepted latest revision 数；
  - 因 stale plan 需要重审的场景数。
- 验收：所有需要起草的场景都有 accepted revision，且依赖不 stale 时，Step 10 才能完成。

### P6：真实一致性检查与兼容清理

#### SF-601：替换假的 Snowflake reviewer

- 目标：每条 trace 对应实际检查报告。
- 主要文件：
  - `backend/app/agents/writing_workflow.py`
  - `backend/app/agents/deepseek_workflow.py`
  - `backend/app/snowflake/validators.py`
  - `backend/app/models.py`
- 验收：返回 `passed/warnings/failed/skipped` 和 findings；未执行时不能出现 checked。
- 验证：trace 与实际 report 一致性测试。

#### SF-602：把 Manuscript consistency 前移到接受前

- 目标：避免先提交再发现 critical 问题。
- 主要文件：
  - `backend/app/analysis/consistency.py`
  - `backend/app/services/manuscript_service.py`
  - `backend/app/data/flows.py`
  - `backend/app/models.py`
  - 对应 Manuscript proposal review 组件
- 验收：proposal 在接受前显示检查结果；critical finding 阻止接受或要求带理由 override；post-accept outbox 检查继续保留。
- 验证：pre-accept、override、post-accept 防御性复查测试。

#### SF-603：废弃兼容接口和 legacy 字段

- 前提：前端和导入/导出全部迁移完成。
- 候选清理项：
  - 旧 `/snowflake/generate` 自动保存语义；
  - `snowflake_artifacts` UPSERT 写入口；
  - Step 10 Snowflake manuscript 生成规则；
  - `open_threads` 自由文本作为生成依据；
  - 无实际检查的 reviewer trace。
- 验收：没有生产调用者依赖旧语义；备份和恢复仍能处理历史数据。

## 10. 项目结构与所有权边界

建议结构：

```text
backend/app/snowflake/
  step_spec.py          # 十步定义、依赖和 optional 元数据
  contracts.py          # 分步骤领域输出结构
  validators.py         # 纯验证逻辑，不访问数据库
  dependencies.py       # 依赖闭包、upstream snapshot、stale 计算

backend/app/services/
  snowflake_service.py          # application orchestration
  snowflake_compile_service.py  # Step 7/8 编译和 proposal 创建

backend/app/data/
  repositories/snowflake.py     # revision/head SQL
  flows.py                       # accepted decision 原子事务

frontend/src/stores/
  snowflake.ts           # 迁移期 facade/coordinator
  snowflake/             # 规模需要时再按 artifacts/revisions/compiler 拆分
```

边界规则：

- Router 只做 HTTP 输入输出和错误映射。
- Service 负责编排，不直接写 SQL。
- Repository 只实现持久化，不调用 provider、Wiki 或前端概念。
- Validator 是纯逻辑，可在 provider 输出、人工接受和导入时复用。
- Provider 只返回候选内容，不接触 review state 或数据库提交。
- Outbox 只处理 accepted revision 的派生工作。

## 11. 测试策略

### 11.1 后端单元测试

覆盖：

- 十步 schema valid/invalid cases；
- dependency closure 和 stale propagation；
- revision 状态机；
- optimistic concurrency；
- Scene Contract blocking rules；
- StoryThread proposal 转换；
- legacy migration；
- consistency finding/override。

### 11.2 后端集成测试

核心场景：

1. Generate 只创建 pending revision。
2. Accept 后原子更新 head、步骤、stale 和 Outbox。
3. Reject 不改变 accepted head。
4. 修改 Step 2 后 Step 4/6/8/9 失效。
5. Step 8 接受场景和线程后，Manuscript generation context 可见这些结构化数据。
6. Step 10 不再创建 Snowflake manuscript Artifact。
7. critical consistency finding 阻止 Manuscript proposal 接受。

### 11.3 前端测试

覆盖：

- Draft/Pending/Approved/Stale/Skipped 状态显示；
- revision 切换、接受、拒绝和并发冲突；
- impact preview；
- blocking proposal 不被默认选择；
- Step 10 跳转和完成度；
- 本地草稿恢复不会覆盖 accepted revision。

### 11.4 E2E 场景

```text
创建项目
  -> 完成并接受 Step 1–3
  -> 修改并接受 Step 2
  -> 验证下游 stale
  -> 重新接受 Step 4–8
  -> 审核 Scene/StoryThread proposals
  -> 按场景生成 Manuscript proposal
  -> consistency 检查
  -> 人工接受
  -> 产生 ManuscriptRevision、Wiki observed evidence 和 writeback proposals
```

### 11.5 实施阶段验证命令

本计划编写阶段不运行这些命令。每个实现任务完成后运行相关子集，阶段结束运行全部：

```powershell
Set-Location backend
rtk uv run --frozen --extra dev python -m unittest discover -s tests
rtk uv run python -m compileall app

Set-Location ..\frontend
rtk pnpm test
rtk pnpm build
```

如果依赖未安装，应明确报告，不能把未执行的检查描述为通过。

## 12. 数据迁移策略

### 12.1 现有 Step 1–9 Artifact

- 每行回填为 `revision_no=1`、`source=legacy`、`status=accepted`。
- 设为当前 accepted head。
- 用迁移时的全部 accepted heads 生成初始 upstream snapshot。
- 不重新解析或改写原正文。

### 12.2 现有 Step 10 Artifact

- 回填为 `source=legacy`、`status=draft` 或专用 `legacy_draft`。
- 不设为正式 Manuscript head。
- 不自动改成 approved Wiki evidence。
- 提供人工拆分/导入流程。

### 12.3 现有 compiler runs 和 proposals

- 保留 `analysis_runs`、Scene Proposal 和 Writeback Proposal 历史。
- 已接受 proposal 不回退。
- 尚未结束且来源 Artifact 已变化的 proposal 标记 `superseded`。

### 12.4 备份兼容

- 先扩展 backup manifest 和 restore validation，再启用新表写入。
- 旧备份导入时执行同一套 legacy backfill。
- 新备份必须明确声明 Snowflake revision schema version。

## 13. 风险与缓解

### 13.1 数据模型迁移风险

风险：现有 `snowflake_artifacts` 同时被 API、Wiki 和测试依赖。

缓解：先增加 revision/head 表；保留旧表作为 accepted projection；等所有读取者迁移后再考虑移除。

### 13.2 stale 级联过度

风险：任何小改动都使大量下游步骤失效，造成作者疲劳。

缓解：记录具体依赖 revision；允许人工“review and reaffirm”；后续可以按字段级依赖细化，但首版先保证正确性。

### 13.3 结构化契约降低创作自由度

风险：编辑器变成表单，破坏写作体验。

缓解：保留 Markdown/自由文本投影；结构化字段用于依赖、验证和生成，不要求作者只能使用表格编辑。

### 13.4 Step 10 迁移导致旧草稿难以定位

风险：旧大文本无法自动可靠拆分为场景。

缓解：只读保留；提供人工选区导入 proposal；禁止自动提交。

### 13.5 接受前一致性检查误报

风险：简单文本规则阻止合理创作。

缓解：区分 warning/critical；critical 规则必须可解释并携带证据；支持带理由人工 override；保留审计记录。

## 14. 实施边界

### Always

- 所有 schema 变更使用版本化 SQLite migration。
- 所有 accepted decision 使用事务和 optimistic concurrency。
- 所有 provider 返回值在边界验证。
- 保留作者历史内容和审计记录。
- 每个任务都包含回归测试和构建验证。

### Ask first

- 删除或重定义旧公开 API。
- 自动把旧 Step 10 文本拆分并写入 Manuscript。
- 允许绕过 critical finding。
- 增加大型第三方依赖。
- 改变备份格式的向后兼容策略。

### Never

- AI 输出直接更新 accepted head。
- 通过覆盖旧行实现“修订”。
- 自动修改 Canon、StoryThread 或 ManuscriptRevision。
- 为通过测试而删除失败测试或放宽关键业务不变量。
- 把 stale 内容静默视为当前有效内容。

## 15. Definition of Done

全部完成必须同时满足：

- [x] AI generation 只创建 `pending_review` revision。
- [x] 每个 Snowflake 步骤拥有不可变修订历史和 accepted head。
- [x] 上游 accepted revision 变化会传递标记下游 stale。
- [x] UI 不再把存在记录简单等同于 Saved/Approved。
- [x] Step 2、3、4、7、8 拥有明确且可验证的结构化契约。
- [x] Step 9 可以显式跳过。
- [x] 第 6–9 步支持记录式分页和局部生成。
- [x] Scene Contract 的关键字段缺失会阻止接受。
- [x] Step 8 可以创建可审核的 StoryThread/Event proposal。
- [x] Manuscript 生成能读取已接受的 StoryThread 和线程事件。
- [x] Snowflake Step 10 不再产生独立 manuscript blob。
- [x] Step 10 完成度来自 accepted ManuscriptRevision 覆盖率。
- [x] consistency reviewer 返回真实 findings，critical 问题在接受前可见。
- [x] 旧 Step 1–9 内容无损迁移，旧 Step 10 内容可恢复且不被自动批准。
- [x] 后端测试、前端测试、编译和构建全部通过。

## 16. 已采用的实施决策

1. 人工 Save 只创建 draft；批准使用独立 Accept 操作。
2. Scene Contract 关键字段和未解析 Required Canon 由服务端 blocking quality gate 判定。
3. 当前不提供 critical finding override；作者必须修订内容后再接受。未来若增加 override，必须单独设计理由、操作者和时间审计。
4. 旧 Step 10 Artifact 采用人工选段并导入 pending Manuscript proposal，不做自动切分或自动批准。
5. stale 主链保持步骤级；Step 6–9 的内容存储和生成粒度为记录级。
6. 第 7 步世界资料保留为相邻的 World Bible record，与 Character Profile/Canon 写回边界分离。

## 17. 首批执行清单

首批任务已按以下顺序完成：

1. SF-001：建立 SnowflakeStepSpec。
2. SF-002：修复 lifespan-aware compiler route test fixture。
3. SF-101：添加 revision/head 数据模型和无损迁移。
4. SF-102：实现 pending -> accepted/rejected 事务。
5. SF-103：前端切换到明确的 revision review 状态。

这五项已通过阶段验收，后续 stale、结构化契约和 Step 10 合流也已完成。
