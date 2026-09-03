# Narrative Graph + LLM Wiki CLP 最终收官审计

> 审计日期：2026-08-30
>
> 审计分支：`integration-graphify-clp`
>
> 审计基线：`8571dc9 refactor: seal provider manuscript snapshot boundary`
>
> 审计范围：`docs/older/narrative-graph-clp-integration-plan.md` 的 P0–P11 与第 12 节七条成功标准。

## 1. 最终结论

**结论：通过。**

P0–P11 已形成完整、可执行且有 contract test 保护的集成边界。第 12 节七条成功标准全部满足，当前剩余阶段数为 **0**，本次审计没有发现需要新增 P12 的生产功能缺口。

本结论只针对 Narrative Graph + CLP 集成计划，不表示整个 AI Writing Studio 产品路线图中的所有未来功能均已完成。

## 2. 审计方法

本次审计没有仅依据阶段说明或提交信息判断完成度，而是同时检查：

1. 权威写入调用链、SQLite transaction、Review 与 Outbox handler。
2. Narrative Domain、Graph projector、Snapshot、Director、CLP port/adapter 的实际实现。
3. local 与 provider Manuscript generation、scene-scoped cognition、Reference compatibility surface。
4. 旧 `/projects/{project_id}/graph/analysis` API 与前端 Graph 页面是否拥有或反向修改权威状态。
5. P0–P11 的 contract tests，以及新增的 Graph/cognition 不可用模拟终验。
6. 不使用真实 API key 的 provider、CLP、Graph 与 cognition 模拟动作。
7. 后端全量测试、前端 contract tests、浏览器流程、lint、compile 与 production build。

## 3. 第 12 节成功标准审计矩阵

| # | 成功标准 | 结论 | 主要证据 |
|---|---|---|---|
| 1 | 正式状态只存在一套权威 Domain | PASS | Narrative Domain、Canon、Manuscript 与 Review commit 均落在 SQLite；Graph、Snapshot、Director、cognition 与 CLP 只读取、投影或产生 proposal。 |
| 2 | Narrative Graph 可完全从 SQLite 重建 | PASS | `NarrativeGraphProjector` 每次从 SQLite relations 投影；重建测试证明临时 graph-only 边会消失，新增 SQLite relation 会进入新图。 |
| 3 | 任意 Scene 的 Snapshot 时间与知识隔离正确 | PASS | Snapshot contract 覆盖 future Scene、future/expired fact、future relation、reader/POV/related-character knowledge、accepted manuscript、Memory、legacy Canon temporal fields 与 provider 输入。 |
| 4 | StoryThread lifecycle 不依赖 `open_threads` | PASS | lifecycle 由 `StoryThread + StoryThreadEvent` 确定性计算；generation、Reference 与 advisory Graph 均忽略 legacy `open_threads`，structured thread 仍可见。 |
| 5 | CLP 产生 evidence-backed typed candidates，不能绕过 Review | PASS | CLP candidate schema 强制非空 evidence、严格 enum 与 `extra=forbid`；结果只 normalize 为 `pending_review` WritebackProposal，接受前不改变 Graph/Snapshot/Director/Domain。 |
| 6 | Graph/cognition/CLP 不可用仍可编辑、保存、回滚和读取 | PASS | P9/P10 覆盖 wake 与 malformed CLP；新增模拟终验让 Graph API 与 cognition writeback processor 独立抛错，accept/edit/restore/read/export 仍成功；浏览器在 Graph 503 时仍完成 Review。 |
| 7 | 外部组件可替换且无需迁移权威模型 | PASS | provider、KnowledgeCompiler、cognition 均通过应用自有 Protocol/DTO/registry 边界接入；测试替身可直接替换实现；旧 Graph API 只返回应用模型且不写 authority。 |

## 4. 逐项证据

### 4.1 唯一权威状态

权威写入仍集中在 SQLite data/repository/flow 层：

```text
Author / accepted proposal
→ validation / Review transition
→ SQLite transaction
→ authoritative Domain / Manuscript
→ same-transaction Outbox jobs
```

`app.narrative` 只从 `WritingDataStore` 读取并构造不可持久化的 Graph、Snapshot 与 Director report。`app.cognition` 返回 `ContextPacket` 或 `WritebackProposalCreate`，不直接写 Narrative Domain。CLP adapter 只返回应用自有 candidate DTO，随后由 `AnalysisService` 创建 Review proposal。

`accept_writeback_proposal()` 是 relation/lifecycle candidate 进入权威 Domain 的 gate；只有 `pending_review → accepted` 才会执行 Narrative relation create 或 StoryThread status transition，并在同一事务内记录 Review 结果。

### 4.2 Graph 可重建

`NarrativeGraphProjector` 从 SQLite `NarrativeRelation` 全量投影到 NetworkX `MultiDiGraph`，Graph 本身不持久化为权威数据。

`test_graph_can_be_fully_rebuilt_from_sqlite_domain` 直接证明：

- 注入原 graph 实例的 derived-only ghost edge 不会出现在重建结果中。
- SQLite 中已有 relation 的 key 与 temporal/provenance metadata 保持一致。
- 后续写入 SQLite 的 relation 会在下一次 projection 中出现。

### 4.3 Snapshot 时间与知识隔离

`NarrativeSnapshot.for_scene()` 是 scene-safe context 的统一入口。现有 contract tests 覆盖：

- 只加载目标 Scene 之前的 accepted manuscript 与 scene-scoped Memory。
- future Scene Contract 不进入 scene-scoped cognition/provider 输入。
- future StoryFact 与 future NarrativeRelation 只记录 withheld count/id，不输出其值。
- expired fact/relation 在目标 Scene 不可见。
- world truth、reader knowledge、POV knowledge 与 related-character knowledge 使用独立时钟。
- reader-only 与 POV-only fact 均不会被错误写入 prose context。
- legacy Canon `current_state` / `last_seen` / `timeline_notes` 不进入 scene-safe compatibility projection。
- local 与 provider Manuscript generation 使用同一个 Snapshot context；provider 收到的 Scene projection 还会清空 legacy `open_threads`。

### 4.4 Structured StoryThread lifecycle

Scene Snapshot 根据目标 scene 之前的 `StoryThreadEvent` 重建 active lifecycle，而不是信任当前全局 status 或 `SceneContract.open_threads`：

- `plant` 建立已种下状态。
- `reinforce` / `misdirect` / `escalate` / `partial_payoff` 推进 developing 状态。
- 目标 Scene 之前的 `payoff` 终止 active 状态。
- 未来 payoff 不会反向污染历史 Snapshot。
- Director 对 overdue、premature payoff、dormant/stalled、isolated thread 与 community suggestion 做 advisory 分析，不修改 Domain。

Snowflake 1–9 的 `open_threads` 字段仍作为旧项目输入兼容面保留，但不再驱动 scene generation、scene Reference 或 graph thread risk。

### 4.5 CLP evidence、typed candidate 与 Review

应用侧 CLP contract 具备以下强约束：

- `CompilerEvidence.source_ref` 与 `excerpt` 均非空。
- entity/relation/lifecycle candidate 至少包含一条 evidence。
- relation 与 lifecycle 使用应用定义的 typed enum。
- temporal interval、confidence 与 lifecycle transition 会在 Pydantic boundary 校验。
- candidate schema 禁止未知字段和后端 action 注入。
- sidecar response 的 project/revision/profile/compiler identity 必须与 request 对齐。

模拟 `RecordingCompiler` 产生 relation 与 lifecycle candidates 后：

- candidates 首先成为 `pending_review` proposals。
- pending candidates 不改变 Narrative Graph、Snapshot、Director 或 StoryThread status。
- rejected candidates 不改变 Domain。
- 只有显式 accepted Review 才写入 relation 或 lifecycle transition。
- sidecar failure 只标记 CLP job/run failed；retry 可恢复且不重复产生 proposal set。

### 4.6 Graph、cognition 与 CLP 故障隔离

已有 P9/P10 contract 分别证明：

- authoritative commit 后的 dispatcher wake failure 不会误报或回滚已提交写入。
- malformed CLP configuration 不阻断 FastAPI startup、authoring/read API 或其他 Outbox jobs；CLP job 保留失败与 retry attempt 语义。

本次审计新增模拟 Graph/cognition 不可用终验：

```text
GET graph analysis        → 500 advisory failure
cognition writeback job   → failed
Manuscript accept         → 200
manual edit               → 200
revision restore          → 200
read scenes/revisions     → 200
export                    → 200
CLP / consistency / Wiki  → succeeded
```

前端浏览器终验还将 Graph API 持续模拟为 503，证明：

- Manuscript proposal 仍能接受。
- Reference suggestion 仍能接受。
- Graph 错误只显示在 Graph workspace，不污染正式 authoring 状态。
- Graph 服务恢复后可手动刷新并重新显示 advisory analysis。

### 4.7 外部组件可替换性

外部实现被限制在应用自有边界之后：

- `WritingProvider` 接收应用自有 request/context/model，不持有 Review commit 权限。
- `KnowledgeCompiler` 接收 `KnowledgeCompilerRequest`，返回 `KnowledgeCompilerResult`。
- cognition 接收 `ProjectCognitionSnapshot` / `WritingScope` / `CommittedContentEvent`，返回 context 或 proposal。
- Graph API 返回应用自有 `GraphAnalysisResponse`。

Capturing provider、`httpx.MockTransport` CLP adapter、Recording/Unavailable compiler 与 Unavailable cognition 均可在不迁移 SQLite schema、Canon、Manuscript、StoryFact、StoryThread 或 NarrativeRelation 的情况下替换正式实现，直接证明边界可替换。

## 5. 候选缺口裁决

### Provider Manuscript Snapshot boundary

这是 P10 后确认的真实缺口，已作为 P11 修复并由 provider input-capture contract 固化。原始 `SceneContract.open_threads` 已不能绕过 Snapshot context 进入 provider。

### 旧 `/projects/{project_id}/graph/analysis`

审计结论：**保留为安全 advisory compatibility surface，不新增 P12。**

理由：

- 它只读取应用构造的 `ProjectCognitionSnapshot`。
- graph module 没有 data store 或 SQLite write capability。
- response 是应用自有 DTO，不暴露第三方 Graphify schema。
- legacy `open_threads` 已不产生 thread risk、Canon mention 或 unresolved count。
- API 失败不会阻断 authoring，前端只显示局部 graph error。

该页面尚未展示新的 Narrative Graph traversal 或完整 Director report，属于后续产品能力增强，而不是本集成计划“唯一 authority、可重建、隔离、Review、故障隔离、可替换”成功标准的缺口。

### 其他候选

没有发现比 P11 更晚的真实功能边界缺口。没有为了继续编号而新增抽象或迁移 project-scoped Reference/Writeback compatibility surface。

## 6. 模拟替代真实认证

本次终验未使用真实 API key 或外部账户，使用以下可重复替身：

- provider：`ProviderRegistry + CapturingProvider`，捕获 Manuscript scene/context 并返回固定草稿。
- CLP HTTP：`httpx.MockTransport`，模拟成功、timeout、connection error、server error、malformed JSON 与 identity drift。
- CLP pipeline：Recording/Empty/Flaky compiler，模拟 candidates、zero-candidate cache、failure 与 retry。
- CLP configuration：环境变量注入 malformed timeout，模拟 adapter construction failure。
- Graph/cognition：Unavailable graph/cognition adapter，模拟 API 与 Outbox processor 故障。
- 浏览器：Playwright route mock，模拟 Graph 503、局部错误显示与恢复刷新。

这些替身验证的是应用 contract、authority boundary、Review gate 与 failure semantics。它们不等价于某一具体云厂商的网络连通性或计费账户 smoke test，但该外部连通性不属于本地集成架构的收官阻断项。

## 7. 验证结果

- Backend full suite：203 tests OK。
- CLP focused：20 tests OK。
- Narrative focused：30 tests OK。
- StoryThread boundary：3 tests OK。
- Scene cognition boundary：1 test OK。
- Provider Manuscript Snapshot boundary：1 test OK。
- Authoring failure isolation：3 tests OK。
- Frontend contract suite：27 tests OK。
- Frontend mocked browser review loop：passed。
- 修改范围 Ruff：passed。
- Ruff format check：passed。
- `python -m compileall app`：passed。
- Frontend ESLint：passed。
- Frontend production build：passed。
- `git diff --check`：passed。

## 8. 非阻断残余与明确保留面

以下内容不影响收官结论：

- Snowflake 1–9 `open_threads` 输入兼容。
- LocalFileLlmWiki source/evidence ingestion。
- project-scoped Reference / Writeback cognition 的 legacy project snapshot compatibility surface。
- Snowflake 1–9 的 LocalFileLlmWiki source/evidence retrieval。
- 旧 Graph 页面未直接呈现新的 Director/traversal 功能。
- 测试运行仍会显示 FastAPI/Starlette 的既有 deprecation warning；本阶段没有进行无关依赖迁移。

## 9. 收官声明

Narrative Graph + LLM Wiki CLP 集成计划现在满足以下最终结构：

```text
SQLite Narrative Domain = 唯一权威状态

SQLite Domain
├─ deterministic projection → Narrative Graph
│  ├─ Snapshot
│  ├─ Director
│  └─ Retrieval / advisory analysis
│
└─ accepted Manuscript Revision
   └─ CLP extraction
      └─ typed evidence-backed candidates
         └─ WritebackProposal
            └─ validation
               └─ human Review
                  └─ accepted commit
                     └─ SQLite Narrative Domain
```

**最终判定：P0–P11 完成，七条成功标准 7/7 PASS，剩余 P = 0。**
