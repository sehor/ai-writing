# 修复保存已有记录后的 dirty 基线和离开保护

处理状态：已完成（2026-09-07）。Canon、Memory、Chapter、Scene 保存绑定请求 ID/scope/选择代次与快照；成功只确认该快照，保留新增输入，只有创建后确实切换 ID 才使用保护豁免。章节与场景分别维护豁免标志；同步监听保护立即切换，并保留拒绝离开时的内容。20 项 Pinia 回归覆盖四类表单的成功、失败、新建、继续输入、迟到响应及项目往返。`pnpm test`（32 Node + 61 Vitest）、build、lint 和两条真实后端 E2E 通过。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

已复现：保存已有 Canon C 后再编辑并切到 D，离开确认函数调用数为 0，即使它被设置为拒绝离开也直接切换；刚保存完成后 isScopeDirty 仍为 true。原因是 active ID 未变化，suppressNextSelectionGuard 没被 watcher 消耗，保存基线也未更新。

**涉及位置**

- `frontend/src/stores/canon.ts:164`
- `frontend/src/stores/manuscript.ts:482`
- `frontend/src/stores/manuscript.ts:596`
- `frontend/src/services/draftSessions.ts`
- `frontend/src/stores/memory.ts`

**修复边界**

统一已有记录保存成功后的基线更新和选择保护；覆盖 Canon、Memory、Chapter、Scene 中相同模式。请求发起时捕获目标 ID/scope/快照，保留保存期间继续输入的内容。

**验收标准**

- [x] 保存后无新增修改的草稿变 clean；再次修改并拒绝切换时保留原记录及内容。
- [x] 保存期间继续输入时，仅请求快照变为已保存基线，新增内容仍 dirty。
- [x] 保存期间切记录/项目时，迟到响应不能清除新编辑器缓存或更改新选择。
- [x] 新增记录与编辑已有记录的保护行为一致。

**验证要求**

Pinia 行为测试覆盖成功、失败、迟到响应及继续输入；pnpm test、pnpm build。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-01。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
