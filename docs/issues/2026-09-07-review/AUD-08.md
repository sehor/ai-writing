# 支持 Step 8 回改后的场景更新提案与冲突审核

**处理结果（2026-09-07）**：已修复，代码与本记录同一提交。来源映射决定新增或更新；更新提案保存来源 revision、目标 plan_version 和字段差异，接受操作在 BEGIN IMMEDIATE 事务中重新检查二者。序号互换可原子应用，真实碰撞整批回滚；重复接受和已落地来源的重编译不产生重复场景。界面展示差异和冲突提示，原场景 ID、正文及历史保留；规划版本领先正文时显示待核对并影响完成状态。

迁移 15 为旧提案保留新增语义，已有正文从迁移时的规划版本开始跟踪；后续人工接受、保存或恢复正文会记录当时的规划版本。未猜测旧场景来源。验证：新增 4 项 SQLite 回归；全部 310 项后端测试，Ruff lint/format、compileall 通过；前端 32 项 Node + 63 项 Vitest、lint/build 和 3 条 E2E 通过。新增浏览器回归覆盖回改、差异审核、目标冲突、重新编译、稳定 ID/历史和正文过期提示。使用隔离数据库及合成文本，无真实模型调用。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

已复现：接受 scene-opening → 编译并接受 scene 1 → 修改同一 record 的 outcome 并接受 → 再编译，接受时抛 SceneSequenceConflictError，已有场景仍保留旧 outcome。当前落地流程只有新增。

**涉及位置**

- `backend/app/services/snowflake_compile_service.py:177`
- `backend/app/data/flows.py:552`
- `backend/app/data/repositories/scene_proposals.py`
- `backend/app/routers/snowflake.py`
- `frontend/src/components/snowflake/SnowflakeRecords.vue`
- `frontend/src/stores/snowflake.ts`

**修复边界**

以稳定来源映射区分 create/update，生成字段级差异和目标基线，人工接受后更新已有 SceneContract。处理作者手工改场景与上游回改之间的冲突、幂等重编译和下游过期状态。

**验收标准**

- [x] 同一 record 回改并接受后更新原 scene，ID、正文历史及引用不变。
- [x] 目标被手工编辑后不得静默覆盖；显示冲突并要求基于最新内容重新审阅。
- [x] 重复编译/重试无重复场景或重复副作用；无关 record/场景不受影响。
- [x] 存在真正的序号碰撞时仍阻止提交，批量应用原子化。
- [x] 计划更新后，受影响正文的 readiness/stale 提示不能继续假装与新规划一致。

**验证要求**

record→compile→accept→edit record→update proposal→accept 的 SQLite 与浏览器回归；冲突、重试和历史保留测试。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-03、AUD-07。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
