# 实现选中文本发起 Copilot 求助的上下文契约

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

完成度缺口：目前 ReferenceWorkspace 依赖独立表单填写问题和范围，未实现 PRD 场景 B 的选中文本求助。已接受建议只更新状态，没有编辑上下文闭环。

**涉及位置**

- `frontend/src/components/manuscript/AcceptedManuscript.vue`
- `frontend/src/components/manuscript/ManuscriptProposalWorkspace.vue`
- `frontend/src/components/manuscript/ReferenceWorkspace.vue`
- `frontend/src/stores/reviews.ts`
- `backend/app/models.py`
- `backend/app/services/reference_service.py`
- `backend/app/agents/reference_workflow.py`

**修复边界**

从正式正文编辑草稿及待审核草稿捕获选区、原文快照、scene/proposal ID 和版本，发起结构化参考请求。只负责请求/生成上下文，应用建议在后续 issue。

**验收标准**

- [x] 选区文本、作者意图和当前场景进入实际生成请求；没有选区时有明确整段/整场景策略。
- [x] 切项目/场景或发生版本变化后，不把旧选区附着到新编辑器。
- [x] 模型输出继续是参考提案，不直接修改正文/Canon；保留来源。
- [x] 本地/Fake 路径可离线验证，真实 provider 保持兼容。

**完成记录（2026-09-07）**

两类编辑器共用 CopilotEditor，捕获 UTF-16 选区或明确的整场景快照；临时 copilotContext 只管理来源，不持有正文保存权。参考面板自动打开并带入场景/原文，内容、版本、目标或会话变化后阻止旧请求；异步响应不能激活到已切换的编辑器。

后端核对项目、场景、提案状态与正文版本，实际 prompt 加入作者意图、选区及周边文本；本地/Fake/provider 共用路径。ReferenceSuggestion 保留结构化 editor_context，迁移 17 及旧备份 null 兼容。API/重开数据库/备份和 Fake 实际 prompt 共 7 项回归，前端新增 9 项捕获/过期/异步行为测试；真实浏览器覆盖两类草稿，确认不自动保存正文。

全量后端 350 项测试、Ruff check、228 文件 format check、compileall 通过；前端 31 项 Node + 90 项 Vitest、lint/build 和 4 条 E2E 通过。截图 `.tmp/copilot-selection.png` 已检查。未进行真实付费模型效果验收。契约见 `docs/copilot-selection-contract.md`，应用/撤销留给 AUD-17。

**验证要求**

选区捕获组件测试、实际 prompt 验证及一次选区→建议浏览器场景。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-01、AUD-02。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
