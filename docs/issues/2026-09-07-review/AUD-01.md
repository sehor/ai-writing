# 修复跨记录切换时自动保存写错草稿缓存

处理状态：已完成（2026-09-07）。自动保存入队时冻结 JSON 快照并绑定 editor session，立即标记 dirty；同步持久化和重置基线都会取消旧定时器。6 项虚拟计时器/Pinia 回归覆盖 Canon 防抖前后 A→B→A、Memory/Chapter/Scene 切换、离开 flush、store 卸载和缓存写失败。`pnpm test`（32 Node + 41 Vitest）和 `pnpm build` 通过。沿用现有 localStorage 格式。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

已复现：编辑 Canon A，在 400ms 防抖触发前确认切换到 B，推进计时器后 canon:A 的缓存内容变成 B。queueAutosave 固定了 scopeKey，但延迟执行的 read() 读取共享 draft ref 的最新值。

**涉及位置**

- `frontend/src/services/draftSessions.ts:64`
- `frontend/src/stores/canon.ts:69`
- `frontend/src/stores/memory.ts`
- `frontend/src/stores/manuscript.ts`

**修复边界**

修复自动保存的值、scope、编辑会话绑定以及旧 scope 定时器的取消/flush；检查同一 helper 的所有调用方。不在本 issue 做 store 大拆分。

**验收标准**

- [x] 编辑 A 后立即切 B，A 的缓存始终保留 A 的作者修改，B 不受影响。
- [x] A→B→A、切换项目、组件卸载及页面关闭均不会串写或由旧定时器覆盖已 flush 的快照。
- [x] 覆盖防抖前后切换及缓存写失败；失败应保留 dirty 状态。

**验证要求**

Vitest 虚拟计时器 + 真实 Pinia stores 的行为测试；pnpm test、pnpm build。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
