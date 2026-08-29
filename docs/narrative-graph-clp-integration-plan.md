# Narrative Graph + LLM Wiki CLP 集成改造计划

> 日期：2026-08-29  
> 目标：在不破坏现有 AI Writing Studio 权威数据模型和人工 Review 流程的前提下，引入 Graphify 的图计算思想与 LLM Wiki CLP 的 typed lifecycle / knowledge compiler 能力。

## 1. 总体原则

采用以下架构：

```text
Graphify：内化图模型与分析思想
LLM Wiki CLP：独立 Sidecar / Adapter
SQLite Narrative Domain：唯一权威状态
```

禁止让 Graphify 或 CLP 直接成为 Canon / Manuscript 的最终存储。

所有外部推断必须遵循现有业务规则：

```text
AI / Compiler proposal
→ validation
→ human review
→ commit
```

派生图、索引、CLP workspace 允许失败或重建，不能影响正式小说状态。

---

## 2. Graphify 集成策略：内化，不整体依赖

不直接把 Graphify 作为核心运行时依赖，也不 fork 整个项目。

只吸收这些能力：

- Node / Edge / Hyperedge 思想。
- 有向多关系图。
- `EXTRACTED / INFERRED / AMBIGUOUS` 来源与置信度机制。
- path / neighborhood / reverse affected traversal。
- community / structural analysis。
- 增量 fingerprint 与可重建 projection 思想。

推荐正式依赖仅增加 `networkx`，应用自己维护 Narrative Graph API。

建议模块：

```text
backend/app/narrative/
    models.py
    repositories.py
    projector.py
    graph.py
    snapshot.py
    director.py
    ports.py
```

Graph 数据由 SQLite 权威数据确定性投影：

```text
SQLite Domain
→ NarrativeGraphProjector
→ NetworkX MultiDiGraph
→ Snapshot / Director / Retrieval
```

Graph 本身必须可随时删除和重建。

---

## 3. Narrative Domain：先建立自己的领域模型

Graph 和 CLP 接入前，先定义应用自己的小说领域对象。

第一阶段建议增加：

```text
StoryFact
KnowledgeState
StoryThread
StoryThreadEvent
NarrativeRelation
```

### StoryFact

```text
subject
predicate
value
valid_from_scene
valid_to_scene
source_ref
status
```

### KnowledgeState

区分：

```text
world_truth
reader_knowledge
character_knowledge
```

必须能够表达：

```text
某事实从 Scene 1 就为真
读者 Scene 80 才知道
角色 A Scene 84 才知道
```

### StoryThread

```text
type
status
planted_at
target_payoff_from
target_payoff_to
importance
reveal_constraints
```

### StoryThreadEvent

```text
scene_id
action = plant | reinforce | misdirect | escalate | partial_payoff | payoff
```

这些对象由 AI Writing Studio 自己定义，不能由 Graphify graph schema 或 CLP profile 反向决定。

---

## 4. Narrative Graph Core

为应用增加轻量 Narrative Graph 层。

建议统一接口：

```text
neighbors(node)
path(source, target)
ancestors(node)
descendants(node)
affected(node)
subgraph(scope)
```

建议 Node 类型：

```text
Character
Location
Item
Event
Scene
StoryFact
Secret
StoryThread
Arc
KnowledgeSubject
```

建议 Edge 类型：

```text
CAUSES
CHANGES_STATE
KNOWS
HIDES_FROM
LOVES
HATES
OWES
PLANTED_AT
REINFORCED_AT
MISDIRECTED_AT
PAYS_OFF_AT
REFERENCES
CONTRADICTS
```

每条 relation 至少支持：

```text
source
target
relation
valid_from
valid_to
confidence
source_ref
status
```

图必须使用有向、多边语义；同两个节点可以存在多种关系。

---

## 5. Narrative Snapshot

Graph Core 稳定后，建立唯一生成上下文入口：

```text
NarrativeSnapshot.for_scene(scene_id)
```

Snapshot 负责从权威 Domain + Narrative Graph 中计算：

- 当前时刻有效世界状态。
- 当前读者知识。
- 当前 POV / 相关角色知识。
- 已发生且相关的事件链。
- 活跃 Story Threads。
- 当前 Scene Contract。
- 安全可见的未来约束。
- 禁止泄露的未来事实。
- 相关 Memory / Style 样本。

后续 Manuscript generation、Reference、Consistency、Director 都统一依赖 Snapshot，不再各自拼接上下文。

---

## 6. LLM Wiki CLP 集成策略：Sidecar + Adapter

不把 LLM Wiki CLP 源码复制进 Python 后端。

将其作为独立本地 Node sidecar，通过稳定窄接口调用。

推荐边界：

```text
backend/app/integrations/
    knowledge_compiler.py   # Python Port
    llmwiki_clp.py          # Adapter
```

Python 侧接口示意：

```text
KnowledgeCompiler
- extract_revision(...)
- propose_entities(...)
- propose_relations(...)
- propose_lifecycle_changes(...)
```

运行形态：

```text
FastAPI
   │ JSON/HTTP
   ▼
LLM Wiki CLP Bridge
   │
   ▼
llm-wiki-compiler
```

优先使用本地 HTTP/JSON bridge；MCP 可留给外部 Agent，不作为应用内部强耦合协议。

---

## 7. CLP 只负责“候选知识编译”

CLP 最适合处理：

```text
Manuscript Revision
→ typed entities
→ typed relations
→ lifecycle transition candidates
→ evidence / provenance
```

例如正文出现：

```text
李小飞开始怀疑陈老板的身份。
```

CLP 可以产生：

```text
CandidateRelation
source = 李小飞
target = 陈老板
relation = SUSPECTS
valid_from = Scene 32
confidence = inferred
source_ref = revision:xxx
```

但不能自动成为 Canon。

必须进入：

```text
CLP Candidate
→ normalize to WritebackProposal
→ application validation
→ human review
→ accepted commit
→ SQLite Narrative Domain
```

---

## 8. CLP Profile 的定位

可以建立项目专用 Profile，例如：

```text
ai-writing-narrative.profile.json
```

定义：

```text
Character
Location
Item
Event
StoryFact
StoryThread
Secret
Scene
Arc
```

以及 typed relations 和 lifecycle，例如：

```text
StoryThread:
planned
→ planted
→ developing
→ paid_off
→ archived
```

但 CLP Profile 只能作为应用 Domain Schema 的投影。

必须通过 contract tests 保证 Python Domain 与 CLP Profile 不漂移。

---

## 9. 最终数据流

```text
Author / AI
    ↓
Manuscript Revision
    ↓ commit
SQLite authoritative state
    │
    ├── deterministic projection ──→ Narrative Graph
    │                                  │
    │                                  ├→ Snapshot
    │                                  ├→ Director Analysis
    │                                  └→ Retrieval
    │
    └── CLP extraction
           ↓
      Knowledge Candidates
           ↓
      Writeback Review
           ↓ accepted
      SQLite Narrative Domain
           ↓
      rebuild/update Narrative Graph
```

SQLite 始终是真相；Graph 与 CLP 都是派生层。

---

## 10. 实施顺序

### P0：Narrative Domain

- StoryFact。
- KnowledgeState。
- StoryThread / StoryThreadEvent。
- NarrativeRelation。
- SQLite migration + repository + tests。

### P1：Narrative Graph Core

- NetworkX MultiDiGraph projection。
- path / affected / neighborhood API。
- source / confidence / temporal edge metadata。
- 图可完整重建测试。

### P2：Narrative Snapshot

- `for_scene(scene_id)`。
- 过去正文跨场景可见。
- 未来事实按 knowledge / spoiler rule 屏蔽。
- Manuscript generation 改用 Snapshot。

### P3：Director Analytics

- StoryThread lifecycle 分析。
- payoff overdue / premature payoff。
- dormant subplot。
- causal chain / isolated thread。
- Graph community 仅作为建议，不自动定义 Arc。

### P4：CLP Sidecar

- 建立 `KnowledgeCompiler` port。
- 启动本地 sidecar。
- Narrative CLP Profile。
- Revision → candidates。
- candidates → WritebackProposal。
- sidecar failure 不影响正文 commit。

### P5：统一旧 LLM Wiki 能力

评估现有 `LocalFileLlmWiki`：

- 保留 source/evidence ingestion 所需部分。
- Snapshot 已覆盖的 retrieval 逻辑逐步迁移。
- 避免 Narrative Graph 与 LLM Wiki 各维护一套事实关系。
- 最终将 Local LLM Wiki 降级为 source/evidence adapter，或在无独立价值后删除。

当前收敛结果：

- `LocalFileLlmWiki` 仅保留 source JSON / Markdown evidence、planned/observed 分类、supersession、Snowflake stage 可见性和 deterministic evidence ranking。
- 删除本地 `wiki/concepts` / `wiki/index.md` 派生知识投影；ingest 时会清理遗留投影，避免与 Narrative Graph / Narrative Domain 形成第二套事实关系。
- `retrieve_context()` 返回 source evidence，不再把 source excerpt 复制成事实/约束。
- `NarrativeSnapshot.for_scene()` 不再调用旧 LLM Wiki retrieval；Scene / Manuscript 连续性、事实、关系、线程全部由 SQLite Narrative Domain + Narrative Graph projection + accepted manuscript 计算。
- 旧 Wiki context / insight API 暂保兼容和 advisory 价值，主要服务 Snowflake 1-9 的 source evidence；不参与 Scene 权威状态判定。
- CLP candidate pipeline 不变：accepted revision -> typed candidate -> WritebackProposal -> validation -> human review -> SQLite Narrative Domain。

### P6：固化 Scene Snapshot 边界

P5 完成后移除 scene-scoped Narrative 路径中的旧 Wiki 兼容注入，避免形成“虽然不调用但仍可注入”的第二上下文入口：

- `NarrativeSnapshot.for_scene()` 不再接收 `llm_wiki`，Snapshot 也不再携带 `wiki_context`。
- Chapter compile、Manuscript proposal、scene-scoped Reference 只依赖 SQLite Narrative Domain + Narrative Graph + accepted manuscript + Memory / Style / cognition context。
- Snowflake 1-9 的旧 Wiki source/evidence retrieval 继续保留，不纳入本阶段迁移。
- Consistency 与 Director 已直接使用 `NarrativeSnapshot`，保持 advisory 语义，不增加写权限。
- CLP、Outbox、Writeback Review 主链保持不变。
- 增加边界 contract test，防止未来重新把旧 Wiki 注入 scene Snapshot。

### P7：固化结构化 StoryThread 边界

P6 后继续收口成功标准 4，避免旧 `SceneContract.open_threads` 与结构化 StoryThread lifecycle 同时驱动 Narrative 行为：

- `SceneContract.open_threads` 暂保留为 Snowflake / 旧项目兼容字段，不做 schema migration，也不删除旧数据。
- Scene Snapshot generation context 不再输出 `open_threads`；活跃线程只来自 `StoryThread + StoryThreadEvent` 的确定性时序计算。
- scene-scoped Reference 的兼容 cognition snapshot 会清空 `open_threads`，防止旧字段经 `describe_scope()` 二次注入。
- 旧 Infra Graph 不再用 `open_threads` 生成 thread risk、Canon mention 或 unresolved-thread fallback；线程统计只看结构化 StoryThread。
- Snowflake 解析/保存仍可读写旧字段，本阶段不改变 authoring 输入契约。
- 不改变 Director、CLP candidate、Writeback Review、Manuscript acceptance 或 Outbox 行为。
- 增加 StoryThread boundary tests，证明旧字符串存在时不会污染 scene generation、Reference 或 Graph，且结构化线程仍正常可见。

### P8：固化 scene-scoped cognition 输入边界

P7 后继续收口成功标准 3 和 7，避免可替换 cognition adapter 通过旧项目级字段绕过 Narrative Snapshot 的时间/知识隔离：

- `NarrativeSnapshot.for_scene()` 先完成 SQLite Domain + Graph 的确定性 scene snapshot，再从该 snapshot 生成 cognition 兼容投影。
- scene-scoped cognition 只接收目标 Scene，不接收未来 Scene Contract。
- 兼容投影继续清空 Canon `current_state` / `last_seen` / `timeline_notes` 与 Scene `open_threads`，避免旧 temporal/current-state 字段重新进入 prose context。
- cognition 可见 StoryThread 只使用当前 scene 计算出的结构化 active threads / prior events；Memory 与 accepted manuscript 继续遵守现有 scene filtering。
- Reference 继续复用同一安全兼容投影，不新增第二套 projection 规则。
- 不改变非 scene-scoped cognition、Snowflake 1–9 source/evidence retrieval、Director、CLP、Review、Manuscript acceptance 或 Outbox。
- 增加 cognition boundary contract test，使用会回显输入字段的 adapter 证明未来 Scene、旧 Canon temporal state 和旧 `open_threads` 均无法经 cognition 重新污染 scene generation，同时结构化 StoryThread 仍可见。

### P9：固化 post-commit Outbox wake failure 边界

P8 后核对成功标准 6，确认正式写入已经与 Graph / cognition / CLP 的实际 job 执行解耦，但 HTTP mutation 在 SQLite 提交完成后仍直接调用 `dispatcher.wake()`；如果派生流水线唤醒本身抛异常，请求会误报 500，尽管权威状态和 outbox jobs 已经成功提交。

- Snowflake artifact save、Manuscript proposal acceptance、accepted Manuscript manual save、revision restore 的 authoritative SQLite commit 保持原有事务语义。
- commit 后的 Outbox wake 改为 best-effort notification；wake failure 只记录 observability event，不回滚、覆盖或误报已经成功的正式写入。
- Outbox jobs 仍在同一权威事务中持久化，dispatcher 的周期 sweep / startup recovery 继续负责后续派生处理，因此不丢 CLP / consistency / cognition / Wiki 后处理任务。
- Manuscript read / revisions / export 继续完全依赖 SQLite，不依赖派生组件可用性。
- 不吞掉正式写入事务、Review validation 或 Outbox job handler 自身的失败；仅隔离 commit 之后的 wake signal。
- 增加 authoring failure-isolation contract test，证明 wake 故障时 save / accept / edit / restore / read 仍成功，且各 revision 的派生 jobs 已持久化等待恢复处理。

---

## 11. 明确不做

第一阶段不要：

- 把 Graphify CLI 直接嵌入请求链。
- 把 `graph.json` 当权威数据库。
- fork Graphify 后维护一个 novel-graphify。
- 把 CLP SQLite / workspace 当正式 Canon。
- 让 CLP 自动接受 lifecycle transition。
- 为图能力立即引入 Neo4j / GraphRAG 等大型基础设施。
- 同时重写现有 Manuscript / Review / Outbox 主链。

---

## 12. 成功标准

完成本计划后，应满足：

1. 小说的正式状态只存在一套权威 Domain。
2. Narrative Graph 可完全从 SQLite 重建。
3. 任意 Scene 都能生成时间与知识隔离正确的 Narrative Snapshot。
4. StoryThread 可以被系统计算生命周期，而不是依赖 `open_threads` 字符串。
5. CLP 能从正文产生带 evidence 的 typed candidates，但无法绕过 Review 修改正式状态。
6. Graphify 或 CLP 不可用时，作者仍可以正常编辑、保存、版本回滚和读取小说。
7. 外部组件未来可替换，而不需要迁移小说权威数据模型。
