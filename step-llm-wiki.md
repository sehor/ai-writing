# Snowflake 与 LLM Wiki 阶段交互协议

## 1. 作用边界

LLM Wiki 是一个独立的小说知识模块，负责：

1. 摄取已经确认的 Snowflake 规划内容和正文修订，建立自己的知识索引。
2. 按当前创作阶段、作用域和故事位置返回有来源依据的约束上下文。
3. 根据已摄取内容返回矛盾、缺口、伏笔、关系变化和灵感连接。

LLM Wiki 不管理主程序的项目快照、Canon、Memory、Scene Contract、Manuscript、cognition registry 或模型配置。主程序只通过接口向它发送内容文档和查询，并接收结构化结果。

## 2. 统一内容标记

所有进入 LLM Wiki 的内容必须携带以下元数据：

```text
project_id
source_kind: snowflake_artifact | manuscript_revision
source_ref
title
content
snowflake_step: 1..10
artifact_type
knowledge_class: planned | observed
status: draft | approved | superseded
version
supersedes
scope
story_position
```

- `planned` 表示作者准备这样写，主要来自 Step 1-9。
- `observed` 表示正文中实际写出的内容，来自被确认的 Step 10 修订。
- `planned` 和 `observed` 必须分别保存和检索，不能互相覆盖。
- 修订替换旧内容时，用 `supersedes` 标记旧来源；默认检索不返回已被替换的版本。
- `story_position` 用来限制正文事实的可见范围，避免后续章节状态污染前文创作。

## 3. 统一交互

每个阶段都使用三类操作：

### Retrieve

生成或润色前，主程序发送：

```text
project_id
snowflake_step
instruction
scope
story_position
spoiler_horizon
```

LLM Wiki 返回：

- 与当前阶段相关的规划证据。
- 截至当前故事位置已经发生的正文事实。
- 必须遵守的连续性约束。
- 每条内容的 `source_ref` 和证据摘录。

### Ingest

内容经用户确认保存后，主程序发送一份带统一标记的内容文档。LLM Wiki 自己解析和维护知识，不回写主程序对象。

### Analyze

主程序可以按阶段和作用域请求洞察。LLM Wiki 返回：

- 冲突或不一致。
- 缺失的因果连接。
- 长期未推进的伏笔。
- 人物关系或状态变化。
- 可以发展的情节连接。

每条洞察必须包含来源依据，并保持建议性质。

## 4. 各阶段协议

### Step 1：一句话大纲 `story_contract`

**Retrieve**

- 用户给出的灵感、类型、主题方向。
- 不加载微观设定或正文细节。

**Ingest**

- 以 `planned` 保存核心故事承诺、主冲突和预期结局方向。

**Analyze**

- 故事承诺是否包含主角、目标、阻力和风险。
- 主题与故事承诺是否明显冲突。

### Step 2：一段式大纲 `plot_seed`

**Retrieve**

- Step 1 的已确认规划证据。

**Ingest**

- 以 `planned` 保存起点、主要灾难、高潮和结局。
- 事件必须标记为“计划事件”，不能视为已经发生。

**Analyze**

- 灾难之间是否有因果关系。
- 结局是否回应 Step 1 的故事承诺。

### Step 3：角色摘要 `character_seeds`

**Retrieve**

- Step 1-2 的故事承诺和计划结构点。

**Ingest**

- 以 `planned` 保存角色目标、动机、冲突、秘密和预期弧线。

**Analyze**

- 角色动机是否足以推动计划灾难。
- 核心角色之间是否缺少冲突关系。

### Step 4：一页纸大纲 `plot_synopsis`

**Retrieve**

- Step 1-3 的相关规划证据。

**Ingest**

- 以 `planned` 保存扩展后的因果链、计划地点、阵营和事件连接。

**Analyze**

- 情节扩展是否偏离核心承诺。
- 角色行动是否真正导致后续事件。

### Step 5：角色视角大纲 `character_pov_lines`

**Retrieve**

- Step 4 的全局规划。
- 当前角色在 Step 3 中的规划资料。
- 与该角色直接相关的计划人物和阵营。

**Ingest**

- 以 `planned` 保存角色的主观认知、隐藏动机和计划关系变化。
- 主观认知不得被标记为客观事实。

**Analyze**

- 不同角色视角之间的认知差异。
- 隐藏动机是否有足够的情节承载点。

### Step 6：扩展大纲 `expanded_plot`

**Retrieve**

- Step 4 的因果骨架。
- Step 5 的角色冲突和视角差异。
- 完成当前扩展范围所需的计划地点、阵营和规则。

**Ingest**

- 以 `planned` 保存更细的世界规则、关键物品和事件链。

**Analyze**

- 世界规则是否互相冲突。
- 新设定是否让既定冲突失效。
- 主线是否存在长时间失焦区间。

### Step 7：完整角色档案 `canon_entities`

**Retrieve**

- 当前角色已有的规划证据。
- Step 5 中该角色的视角大纲。
- 与其弧线直接相关的 Step 6 事件。

**Ingest**

- 以 `planned` 保存外貌、能力、习惯、物品和关系细节。
- LLM Wiki 只建立自己的知识索引，不创建或修改主程序 Canon。

**Analyze**

- 角色能力是否破坏剧情难度。
- 档案细节是否与既有动机、视角或计划事件冲突。

### Step 8：场景列表 `scene_contracts`

**Retrieve**

- Step 6 的相关情节区间。
- Step 7 的相关角色规划。
- 用来分配 POV、地点和事件顺序的证据。

**Ingest**

- 以 `planned` 保存场景顺序、POV、地点、目标、冲突和转折。
- Scene Contract 仍由主程序管理；LLM Wiki 只摄取其内容并建立索引。

**Analyze**

- 情节里程碑是否有场景承载。
- 是否存在连续多个场景没有状态推进。
- 角色或地点是否在长区间内无故消失。

### Step 9：场景扩展 `expanded_scenes`

**Retrieve**

- 当前 Scene Contract 的内容。
- 当前场景所需角色、地点和规则证据。
- 完成当前场景所需的上层结构约束。
- 不提供超出 `spoiler_horizon` 的未来细节。

**Ingest**

- 以 `planned` 保存场景节拍、预期状态变化和计划伏笔。
- 状态变化必须标记为 `expected_mutation`，不能视为已经发生。

**Analyze**

- 场景节拍是否能实现 Scene Contract。
- 计划状态变化是否与更早的规划冲突。
- 伏笔是否有来源、推进点或预期回收位置。

### Step 10：正文 `manuscript`

**Retrieve**

- 当前 Step 9 场景扩展。
- 与当前场景直接相关的规划证据。
- 截至 `story_position` 已经发生的 `observed` 人物、地点、事件、关系和伏笔证据。
- 不返回后续章节才成立的状态。

文风、最近原文和上一句对话由主程序从 Manuscript 或 Memory / Style 提供，不属于 LLM Wiki。

**Ingest**

- 以 `observed` 摄取用户确认的正文修订。
- 提取实际出现的人物、地点、事件、关系、状态变化、伏笔和临时设定。
- 保留原文摘录、修订来源和故事位置。
- 不直接修改主程序 Canon、Memory 或 Manuscript。

**Analyze**

- 正文与当前规划之间的偏差。
- 与此前正文事实的连续性冲突。
- 计划状态变化是否真正发生。
- 新形成但尚未利用的伏笔、关系和情节连接。

## 5. 主程序与模块的组合方式

写作时，主程序分别组装自己拥有的数据：

```text
Snowflake / Scene Contract
+ Canon
+ Memory / Style
+ LLM Wiki.retrieve_context(...)
-> 写作模型
```

保存时，主程序只发送内容增量：

```text
approved Snowflake artifact or manuscript revision
-> LLM Wiki.ingest(...)
-> ingestion report
```

需要灵感或检查时：

```text
stage + scope + story position
-> LLM Wiki.analyze(...)
-> evidence-backed insights
```

主程序依赖接口，不依赖本地文件实现。以后切换外部 Agent 时，只替换接口实现。
