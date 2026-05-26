# AI Writing Studio 设计纲要

AI Writing Studio 应该是一个面向长篇小说的本地优先创作工作台，而不是普通 AI 写作聊天框。

核心目标不是让 AI 一次生成更多文字，而是让作品的规划、正文、正史、记忆、风格、结构和 AI 修改都能被持续维护、审阅和回写。

## 一、框架思想

### 1. 作品状态优先

长篇创作的难点不是单次生成，而是连续写作中的状态一致性。

系统必须长期维护：

- 作品、卷、章、场景和版本
- 人物、地点、物品、阵营、时间线和世界规则
- 已确认事实、未解决伏笔、章节目标和冲突
- 原文片段、章节摘要、叙事节奏和角色语气

### 2. Canon 是事实数据库

Canon DB 是已经确认的故事事实，不是普通笔记。

它用于约束后续写作，例如：

```text
character: 林野
current_state: 右臂受伤，尚未知道师父真实身份
last_seen: chapter_12
forbidden: 不可在 chapter_13 之前知道密信内容
```

Canon 的职责是保证事实正确性。Memory / Style 的职责是保证文字连续性。二者不能混在一起。

### 3. 应用编排 AI，而不是 AI 接管应用

系统应该由应用调用多个专职 Agent，而不是让一个大 Agent 管理全部流程。

应用负责：

- 数据持久化
- 工作流状态
- 上下文组装
- 版本和审阅
- 校验 Agent 输出
- 决定哪些变更可以写回数据库

Agent 负责：

- 生成章节计划
- 起草正文
- 总结章节
- 抽取状态变化
- 检查一致性
- 提出修改建议

关键原则：Agent 只能提出变更，最终 commit 由应用完成，必要时由用户确认。

### 4. 外部工具吸收思想，不作为核心依赖

MemPalace、LLM Wiki、GraphRAG、InfraNodus、Obsidian 等工具可以提供设计参考，但核心数据模型和工作流应由本应用掌控。

建议边界：

- LLM Wiki：吸收知识库和可读导出的思想，落地为 Canon DB + Markdown/JSON 导出
- MemPalace：吸收原文保留和记忆组织思想，落地为 memory store 和 style library
- GraphRAG / InfraNodus：早期实现轻量图分析，成熟后扩展为 graph engine
- Obsidian：保留 Markdown + wikilinks 导出能力

## 二、核心分层

### 1. Project / Manuscript 层

管理作品、卷、章、场景、草稿、定稿和修订历史。

这是传统写作软件的骨架，也是其他系统引用内容的基础。

### 2. Snowflake 层

围绕 Snowflake Method 维护创作规划：

- 一句话故事
- 一段式摘要
- 多段式摘要
- 人物摘要
- 场景列表
- 章节目标

Snowflake artifact 是章节生成和结构检查的上游依据。

### 3. Canon DB 层

维护确认过的故事事实：

- 人物状态
- 地点状态
- 物品状态
- 时间线事件
- 世界规则
- 阵营关系
- 禁止提前泄露的信息

Canon 是写作约束数据库，必须结构化存储。

### 4. Memory / Style 层

维护连续写作所需的风格上下文：

- 原文片段
- 章节摘要
- 角色语气样本
- 场景风格样本
- 叙事节奏
- 常用表达和禁用表达

Memory / Style 不判断事实对错，只帮助生成结果像同一本书。

### 5. Graph / Structure 层

把人物、地点、事件、伏笔、主题和冲突建立为结构关系，用来发现：

- 断线伏笔
- 结构洞
- 孤立角色
- 时间线冲突
- 主线过度集中或长期失焦

图谱只提供分析结论，是否修改由作者决定。

### 6. Chapter Compiler 层

章节编译器是核心应用逻辑。写一章时不直接把需求丢给 AI，而是执行固定 pipeline：

```text
读取 Snowflake 规划
→ 加载相关 Canon 状态
→ 加载前文摘要和风格样本
→ 生成章节计划
→ 生成或修改草稿
→ 检查 Canon 一致性
→ 检查伏笔和时间线
→ 检查风格连续性
→ 生成待审阅修改
→ 用户确认
→ 写回 Manuscript / Canon / Memory / Graph
```

### 7. Agent Orchestration 层

编排多个专职 Agent：

- Planner Agent：生成章节计划
- Drafting Agent：起草正文
- Continuity Checker Agent：检查事实一致性
- Style Editor Agent：润色风格
- Foreshadowing Agent：检查伏笔
- Canon Update Agent：抽取状态更新

所有 Agent 输出都必须带来源、理由和目标写入位置，方便应用校验和用户审阅。

## 三、产品形态

第一屏应该是可用的作者工作台：

```text
左侧：作品 / 卷 / 章 / 场景树
中间：正文编辑器
右侧：AI Copilot + 本章约束 + 角色状态
底部：一致性问题 / 伏笔 / 时间线 / 修改建议
独立视图：Snowflake、Canon、Memory、Graph、Manuscript
```

用户操作不应是笼统的“生成小说”，而应是明确的创作动作：

- 生成本章计划
- 写这一场景
- 检查人物状态
- 检查伏笔
- 润色成某角色视角
- 提交本章状态
- 更新正史库

## 四、软件架构

建议保持前后端分离，并优先做 local-first。

```text
Frontend
- Vue 工作台
- 章节树
- 正文编辑器
- Snowflake 视图
- Canon 面板
- AI 审阅面板
- 版本 diff

Backend
- FastAPI
- 项目数据服务
- Canon 数据服务
- Agent 调度服务
- Chapter Compiler workflow
- 导入导出

Storage
- SQLite
- Markdown/JSON 导出
- 后续可扩展全文检索、向量索引、图关系表
```

优先 local-first 的原因：

- 长篇小说涉及隐私和版权
- 作者需要离线写作能力
- 本地文件和数据库更容易建立掌控感
- 云同步可以后期作为增量能力加入

## 五、MVP 范围

第一版只做最小闭环：

1. 章节编辑器
2. Snowflake 基础规划
3. 人物、地点、物品 Canon 卡片
4. 写章前自动组装上下文
5. 写完后抽取状态更新建议
6. 一致性检查报告
7. 用户审阅后写回 Canon

暂缓内容：

- 真实 AI 生成质量优化
- 复杂 GraphRAG
- 完整 MemPalace 风格库
- 多人协作
- 云同步
- 复杂权限系统

## 六、实施步骤

### 第一步：Canon DB foundation

建立项目、人物、地点、物品等基础数据结构和 API。

目标是让作品事实能被结构化保存、查询、更新和审阅。

### 第二步：Structured Scene Contracts

定义场景输入和输出契约：

- 场景目标
- 参与角色
- 涉及地点和物品
- 前置 Canon 约束
- 预期状态变化
- 待审阅写回项

### 第三步：Chapter Compiler v0

先不接真实 AI，使用固定 workflow 和 mock runtime 跑通流程：

```text
章节目标
→ 上下文组装
→ 草稿占位
→ 状态更新建议
→ 一致性检查结果
→ 用户审阅
→ 写回数据库
```

### 第四步：AI workflow runtime

在 workflow contract 稳定后，再接入真实模型。

要求：

- AI runtime 实现统一接口
- 每个阶段可追踪
- 输出必须结构化
- 不允许 Agent 直接写数据库

### 第五步：Memory / Style store

补充风格样本、章节摘要、角色语气和原文片段索引。

目标是提升长篇连续写作的语气和节奏稳定性。

### 第六步：Graph / Structure analysis

基于已有 Canon、Snowflake 和章节状态建立轻量图分析：

- 角色关系
- 事件链
- 伏笔链
- 时间线
- 结构缺口

### 第七步：Manuscript review workflow

完善版本、diff、审阅和回滚流程。

最终让 AI 修改进入“建议 → 校验 → 人审 → commit”的稳定闭环。

## 七、核心判断

这个产品的护城河不在调用哪个模型，而在：

- 作品状态管理
- Snowflake 创作工作流
- Canon / Memory / Graph 分层
- AI 输出校验和人类审阅
- 长篇项目的持续维护能力

只有这些做好，AI Writing Studio 才会区别于普通 AI 写作工具。
