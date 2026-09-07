# 按职责拆分正文 store 与雪花编辑组件

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

结构观察：manuscript.ts 1,254 行，聚合章节、场景、提案、正文编辑、历史、导出和分析刷新；snowflake store 807 行，SnowflakeWorkspace.vue 805 行。行数只是责任集中线索，本 issue 的目标是职责和依赖清晰。

**涉及位置**

- `frontend/src/stores/manuscript.ts`
- `frontend/src/stores/snowflake.ts`
- `frontend/src/components/ManuscriptWorkspace.vue`
- `frontend/src/components/SnowflakeWorkspace.vue`
- `frontend/src/components/manuscript/`
- `frontend/src/components/snowflake/`

**修复边界**

先划出编辑会话、章节/场景管理、正文提案审阅、版本/导出等职责；保留薄兼容门面，组件按已存在领域职责拆分。分阶段提交，避免同时搬动全部前端。

**验收标准**

- [x] 各模块状态所有权明确；一个保存/选择会话不由多个 store 各自维护。
- [x] 不以跨文件复制共享 ref/布尔标志完成形式拆分，不制造新的循环依赖。
- [x] 所有原有用户行为及 R1/R2 新回归通过。
- [x] 交付简短的依赖图/职责说明，说明为什么每个模块需要依赖另一个模块。

**验证要求**

pnpm lint、test、build、test:e2e；保留有效行为测试，减少仅锁死源码形状的断言。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-06、AUD-08、AUD-11。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

## 完成记录（2026-09-07）

- 第一阶段 `20ad9b7`：正文门面装配结构、已接受正文、提案、编辑会话、历史/导出与统一消息模块。原属性/动作兼容，保存会话和选择 epoch 随行为一起移动。
- 第二阶段：雪花工作区拆为总览、产物编辑、编译审核和正文里程碑/导入组件；导入表单跨步骤存活，保留已有记录及历史组件。
- [职责表与依赖图](../../manuscript-state-boundaries.md)。未引入新依赖、迁移或其他业务行为。snowflake store 内部拆分不在本次扩展。
- 前端 lint、build、30 项 Node 检查和 81 项 Vitest 通过；含原 R1/R2、正文并发回归和新增 8 项装配/组件行为测试。三条隔离 SQLite/FakeModelGateway E2E 验证正文审核/保存、分析失败重试和 Step 8 回改。
