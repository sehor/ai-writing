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
