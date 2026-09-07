# 解除 workspace 与领域 stores 的双向依赖

**处理结果（2026-09-07）**：已修复，代码与本记录同一提交。新增叶子 `projectContext` store，持有项目/步骤/模型选择与刷新请求；workspace 通过相同 refs 保持组件兼容，继续负责离开保护和项目加载。8 个领域 store 直接读取 context，删除旧 `WorkspaceShell` 类型绕行。正文提交后的审核刷新与审核面板的修订读取由类型化端口连接，workspace 负责装配；独立正文编辑器可不装配审核面板。其他跨域加载保留现有单向调用，未引入新状态框架。

验证：新增依赖图检查禁止领域反向导入 workspace 及 store 运行时循环；8 个领域独立装配测试、叶子模型选择测试及迟到审核响应测试通过。总计 33 项 Node + 73 项 Vitest，lint/build 及 3 条 E2E 全部通过，覆盖项目切换、草稿恢复、保存/接受后刷新、分析轮询与重试。未变更后端。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

结构观察：workspace 导入领域 stores，多个领域 store 又直接导入 useWorkspaceStore；manuscript 和 reviews 也双向调用。WorkspaceShell 只是类型边界，未消除运行时依赖。

**涉及位置**

- `frontend/src/stores/workspace.ts`
- `frontend/src/stores/workspaceShell.ts`
- `frontend/src/stores/manuscript.ts`
- `frontend/src/stores/reviews.ts`
- `frontend/src/stores/projects.ts`
- `frontend/src/stores/canon.ts`
- `frontend/src/stores/memory.ts`

**修复边界**

把 active project/model selection 等只读上下文放在叶子 context store；跨域刷新留在应用编排层或显式端口，避免领域 store 反向依赖总 workspace。保持界面行为不变，不引入新的状态框架。

**验收标准**

- [x] 领域 stores 不再通过 workspace 获取 context，manuscript/reviews 的循环依赖被消除或通过明确单向接口隔离。
- [x] 每个领域 store 能在小范围测试装配中独立创建，不要求加载完整 workspace。
- [x] 项目切换、迟到响应、恢复草稿、接受后刷新及分析轮询行为不退化。

**验证要求**

依赖边界检查 + 实际项目切换/审阅行为测试；pnpm lint、test、build、test:e2e。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-01、AUD-02。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
