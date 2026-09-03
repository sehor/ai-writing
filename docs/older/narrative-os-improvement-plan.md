# Narrative OS 改进计划

> 日期：2026-08-29  
> 目标：针对长篇小说的“小说记忆、长线导演、作者声音”三类核心痛点，把现有 AI Writing Studio 从结构化写作工作台继续推进为可计算的 Narrative OS。

## 1. 当前判断

| 维度 | 当前状态 | 主要缺口 |
| --- | --- | --- |
| 小说记忆 | 已有 Canon、Memory、planned/observed、story_position、spoiler_horizon | Canon 仍是“当前状态覆盖”，无法准确查询某章节时刻的事实；上下文编译仍可能泄露未来信息或漏掉跨场景前文 |
| 长线导演 | 已有 Snowflake、Scene Contract、open_threads、Graph | 伏笔/支线/弧线仍是字符串，没有生命周期、回收窗口、节奏指标 |
| 作者声音 | 已有 prose_sample、voice_sample、style_rule | 目前主要是“存样本再喂模型”，缺少按场景检索、风格画像和漂移检测 |

## 2. P0：统一 Narrative Snapshot（最高优先级）

建立唯一的场景生成上下文入口：

```text
NarrativeSnapshot.for_scene(scene_id)
```

必须返回：

- 当前场景时刻有效的 Canon 状态。
- 当前角色可知信息与读者可知信息。
- 相关已发生事件与已接受正文。
- 当前 Scene Contract。
- 允许引用的未来约束，不允许泄露的未来事实。
- 与当前 POV / 场景最相关的 Memory / Style 样本。
- 当前活跃 Story Threads。

同步修正：

- 不再把完整 Step 8 / Step 9 直接塞入正文生成上下文。
- Wiki observed retrieval 允许读取当前场景之前的跨场景正文，不能被 `scope == scene_id` 误过滤。
- 所有正文生成、Reference、Consistency 分析统一复用 Snapshot，禁止各模块自行拼上下文。

**验收：** 重新生成 Scene 20 时，系统能读取 Scene 1–19 的有效事实与正文，但看不到 Scene 21+ 的未来揭示。

## 3. P1：时态 Canon / Knowledge State

把 Canon 从“当前值”升级为“带有效区间的事实”。第一版不必上图数据库，可继续使用 SQLite。

建议新增核心对象：

```text
StoryFact
- subject
- predicate
- value
- valid_from_scene
- valid_to_scene
- source_ref
- status
```

同时区分三种知识状态：

```text
World Truth      世界真实状态
Reader Knowledge 读者已知状态
Character Knowledge 角色已知状态
```

示例：

```text
陈老板 = 狐妖首领
world_valid_from: 1
reader_visible_from: 80
李小飞_known_from: 84
```

现有 `current_state / last_seen / timeline_notes` 保留作编辑摘要，但不再作为唯一事实来源。

**验收：** 任意给定 scene position，系统能稳定回答“此刻世界是什么状态、读者知道什么、某角色知道什么”。

## 4. P2：Story Thread / Director Model

把 `open_threads: str` 升级为真正的一等对象。

建议新增：

```text
StoryThread
- type: foreshadow | mystery | relationship | conflict | promise | subplot
- title
- status: planned | planted | developing | dormant | paid_off | abandoned
- planted_at
- target_payoff_from
- target_payoff_to
- importance
- reveal_constraints

StoryThreadEvent
- scene_id
- action: plant | reinforce | misdirect | escalate | partial_payoff | payoff
```

在此基础上增加最小导演分析：

- 伏笔逾期未回收。
- 支线长期未推进。
- 高重要度 thread 过早结清。
- 连续若干场景缺少主线推进。
- Scene Contract 高潮/转折密度异常，提示节奏过快或过慢。

Graph 改为消费这些结构化对象，而不是仅靠字符串扫描推断关系。

**验收：** 系统能解释“哪个伏笔拖太久、为什么；哪个谜底回收太早、依据是什么”。

## 5. P3：Style Fingerprint + Drift Detection

目标不是“自动润色得更标准”，而是保护作者原有声音。

建立项目级与 POV/角色级 Style Profile，第一版优先使用可解释统计特征：

- 句长 / 段长分布。
- 对话、动作、心理、说明文字比例。
- 标点与省略号习惯。
- 高频词、低频词、禁用表达。
- 修饰词、比喻、成语密度。
- 旁白存在感、叙述距离、信息直述倾向。

样本只从**作者确认或接受的正文**更新。

生成时按 POV、场景类型、相邻章节检索最相关样本；生成后只做“风格漂移报告”，不自动重写。

**验收：** 当新章节明显偏离前文语言分布时，系统能指出具体偏移指标，并由作者决定是否修改。

## 6. 实施顺序

```text
P0 Narrative Snapshot
→ P1 Temporal Canon / Knowledge State
→ P2 Story Thread / Director Model
→ P3 Style Fingerprint / Drift Detection
```

不要先增加更大的模型、更多 Prompt 或更复杂的向量库。当前最有价值的投入是把小说的“状态、知识、伏笔、风格”变成应用可计算的数据。

## 7. 产品边界

继续保持现有原则：

- AI 只能提出变更，不能直接改写 Canon / Manuscript。
- 结构化状态优先于长文本提示词。
- Memory / Style 不承担事实正确性。
- Graph 提供诊断，不替作者做创作决定。
- 风格系统优先保护差异性，不把作者文本统一成“标准 AI 文风”。
