# 建立 Step 8 record 与实际场景的稳定来源映射

处理状态：已完成（2026-09-07）。迁移 14 为场景保存只读 Step 8 record identity、已应用 revision 和 plan_version；唯一索引与来源校验触发器隔离项目/记录，旧场景保持空关联。SceneRepository 提供绑定和稳定来源查询，常规修改保留来源并递增规划版本；备份沿用动态列与共享 reader。新增关联、隔离、改名/改序号、正文历史保留、备份 round-trip 测试，后端全量 306 项通过；Ruff format/check、compileall、前端 build 通过。编译接受时写入来源由 AUD-08 集成。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

审查 R6：已接受的 record 可重新修订，但 SceneContract 的落地关联不足以支持按稳定来源更新，目前主要以 sequence 检查碰撞。本 issue 是修复回改闭环的数据前置。

**涉及位置**

- `backend/app/models.py`
- `backend/app/data/migrations.py`
- `backend/app/data/repositories/scenes.py`
- `backend/app/data/repositories/scene_proposals.py`
- `backend/app/services/backup_format.py`
- `backend/app/services/backup_records.py`

**修复边界**

定义并持久化 project + step + record identity 到 scene 的稳定映射，记录已应用 record revision 及必要目标版本。序号和标题可变，不能作为身份。仅负责领域模型、迁移、查询和备份兼容；更新提案由后续 issue 实现。

**验收标准**

- [x] 同一 record 改名、改序号不丢失已关联 scene ID。
- [x] 不同项目及不同 record 不能误关联同一来源；数据库约束与应用校验一致。
- [x] 旧场景/旧备份不会被猜测性错误匹配；无法确定的来源保留明确的未关联状态。
- [x] 保留所有现有正文、revision、thread event 引用，升级与备份 round-trip 通过。

**验证要求**

迁移、唯一性/跨项目边界及备份恢复测试；不得用删除重建场景完成迁移。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

