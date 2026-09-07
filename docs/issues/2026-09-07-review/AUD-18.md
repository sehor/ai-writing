# 补齐时态事实与角色知识的作者维护接口和更正规则

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

完成度缺口：已有 StoryFact/KnowledgeState 数据和查询接口，但不足以支撑完整的作者维护界面。需要先核对现有创建、赋予知识、查询能力，明确错误事实的更正及其时间/知识边界。此项不是把未测试接口判成已知 bug。

**涉及位置**

- `backend/app/routers/narrative.py`
- `backend/app/models.py`
- `backend/app/data/repositories/narrative.py`
- `backend/app/narrative/snapshot.py`
- `backend/app/services/backup_records.py`

**修复边界**

在既有 Narrative 领域内定义作者更正/撤回事实和角色知识的最小 API；选择可追溯更正或版本策略，保留来源和场景时态。先写简短契约，再补必要实现；不把非确认内容直接升级为事实。

**验收标准**

- [x] 作者能修正错误数据，历史来源可追溯；跨项目 ID 不能越权关联。
- [x] valid_from/to、reader visible、character known-from 的边界有一致校验及可解释查询结果。
- [x] 更正后 snapshot 不泄露未来/读者隐藏/POV 未知事实，关联记录无悬空引用。
- [x] 旧数据库和备份兼容；更正状态能被前端准确展示。

**完成记录（2026-09-07）**

契约见 `docs/narrative-maintenance-contract.md`。补齐事实和知识的更正、撤回、历史 API，使用版本比较与同一 SQLite 写事务保存来源、状态及历史。事实更正后，角色知识须重新确认；撤回从权威查询中排除。API 返回 version/updated_at 和 retracted 状态，管理界面由 AUD-19 承接。

迁移 16 增加版本列和不可变历史，兼容旧备份缺失列/表；新增 12 项回归覆盖并发、回滚、跨项目、时间/知识隔离及迁移/备份。全量后端 331 项测试、Ruff check、194 文件 format check、compileall 通过。

**验证要求**

API、跨项目边界、时间边界、知识隔离、迁移/backup round-trip 测试。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
