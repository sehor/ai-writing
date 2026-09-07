# 将 Copilot 建议以可撤销操作应用到当前草稿

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

完成度缺口：reviews.ts 的 updateReferenceStatus 仅更新建议状态；ReferenceWorkspace 没有插入/替换正文的交互，用户点击接受不会产生可编辑文本变化。

**涉及位置**

- `frontend/src/components/manuscript/ReferenceWorkspace.vue`
- `frontend/src/stores/reviews.ts`
- `frontend/src/stores/proposalDraft.ts`
- `frontend/src/stores/manuscript.ts`
- `frontend/src/components/manuscript/AcceptedManuscript.vue`

**修复边界**

建立独立于接受/拒绝参考状态的“应用到草稿”操作，支持明确目标的插入/替换、预览和撤销。建议内容若非可应用 prose，先让作者选择明确的文本片段。

**验收标准**

- [x] 应用只改当前本地编辑草稿并标 dirty，不直接保存正式版本。
- [x] 应用前核对选区原文、目标 ID、版本/会话，过期时提示重新选择，不能覆盖新文本。
- [x] 可撤销；重复点击不意外重复插入；切换/刷新遵守草稿安全。
- [x] UI 清楚区分采纳建议状态与把文本应用到草稿。

**完成记录（2026-09-07）**

新增独立 `referenceApplication` 协调 store，只把经过验证的文本变化写回既有 `proposalDraft` 或正式正文编辑草稿；原有 watcher 继续负责 dirty、自动缓存和离开保护，不调用任何正式正文保存接口，也没有恢复 `reviews -> manuscript` 运行时依赖。`copilotContext` 仍只维护临时选区来源，但补充“同编辑会话”和“同快照”只读校验供应用流程复核。

应用面板与接受/拒绝状态完全分离。作者必须先明确填写要进入正文的文本，再选择“替换求助原文”或“在求助原文后插入”；预览不修改草稿。实际应用前再次核对项目、场景、proposal、版本、组件会话、完整快照和选区原文。应用后旧快照立即失效，因此重复点击不会再次插入；撤销仅在同一编辑会话、同一目标/版本且正文仍等于刚应用结果时允许，作者继续输入、切换目标或刷新后不会用旧撤销覆盖新文本。

新增 4 项 Vitest，覆盖 proposal/正式正文、dirty/缓存、版本/会话/原文冲突、预览、重复应用、后续作者输入后的撤销保护和 UI 状态解耦。全量前端 31 项 Node + 94 项 Vitest、lint/build 和 4 条 E2E 通过；浏览器场景覆盖两类草稿的选区→建议→预览→应用/重复保护→撤销，并确认 proposal、正式正文和 revision 均未被应用动作直接保存。截图生成于 `.tmp/copilot-reference-apply.png`。未进行真实付费模型效果验收。

**验证要求**

组件/Pinia 版本冲突、撤销、重复应用测试；真实浏览器 PRD 场景 B。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-01、AUD-02、AUD-16。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

