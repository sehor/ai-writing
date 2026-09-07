# 展示正文生成审核材料并建立明确的逐项处理流程

处理状态：已完成（2026-09-07）。独立 GenerationReview 组件展示完整生成材料及来源，逐项标记待处理/已核对/保留疑问，与作者修改稿分离；严重一致性规则沿用后端。标记只保存在当前浏览器本机缓存，不随项目备份跨机器同步，保存失败明确提示。2 项组件行为测试与生成（真实服务+FakeModelGateway）→审阅→刷新→接受的真实 SQLite E2E 通过；全量前端 32 Node + 63 Vitest、build、lint 通过。审核标记不会应用跨领域变更。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

审查 R5：当前作者只能看到 Review N design deviation(s) / Resolve N question(s) 的数量，无法看到实际问题、证据和变更内容。本 issue 负责补齐持久化之后的作者流程。

**涉及位置**

- `frontend/src/components/manuscript/ManuscriptProposalWorkspace.vue`
- `frontend/src/stores/proposalDraft.ts`
- `frontend/src/stores/manuscript.ts`
- `frontend/src/types/index.ts`
- `backend/app/services/manuscript_service.py`

**修复边界**

消费结构化审核载荷，展示偏差的当前设计/建议/理由/影响、事实候选、连续性问题和 coverage。明确待处理、已处理、保留疑问的状态，以及哪些问题阻止接受；只有需要持久化决策时补最小后端接口。

**验收标准**

- [x] 生成后与刷新后都能查看每项内容及来源，不能只展示数量。
- [x] 决定和待处理状态明确，不能因普通 warning 强制阻止作者合理选择；critical 保持现有明确规则。
- [x] 需要应用到其他领域的建议先形成可审核提案，不能直接修改 Canon、规划或正式正文。
- [x] 旧 proposal 缺载荷时展示兼容状态；用户编辑后的草稿与原模型建议清楚区分。

**验证要求**

组件/Pinia 行为测试、后端决策测试（如新增）及生成→审阅→刷新→接受的浏览器场景。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-05。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

