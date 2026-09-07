# 持久化并通过 API 返回正文生成的完整审核材料

处理状态：已完成（2026-09-07）。ManuscriptProposal 新增 generation_review（schema_version=1、来源模型/run、完整原始 material）；迁移 13 添加 JSON 列，旧记录默认 null，旧 prose-only 输出明确标记且不伪造材料。备份沿用共享 reader 与动态列导出，无额外表清单。生成、独立重启、API、备份导入逐字段回归，以及迁移失败回滚/重试等 11 项测试通过；备份安全、模型运行时与正文编辑另 30 项通过。Ruff format/check、compileall、前端 build 通过。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

已复现：模型返回设计偏差和连续性问题，生成成功后 checklist 显示各有 1 条，但重新读取 ManuscriptProposal 时具体内容完全不存在。生成契约中的 coverage、fact candidates 等也没有完整承载位置。

**涉及位置**

- `backend/app/services/manuscript_service.py:197`
- `backend/app/snowflake/contracts.py:642`
- `backend/app/models.py`
- `backend/app/data/repositories/manuscript.py`
- `backend/app/data/migrations.py`
- `backend/app/services/backup_records.py`

**修复边界**

为 ManuscriptProposal 增加版本化结构化生成审核载荷，保存 coverage、entry/exit state、fact candidates、design deviations、continuity questions、source refs；包含 API、数据库迁移和备份兼容。前端展示单列任务。

**验收标准**

- [x] 模拟模型返回每类审核材料，生成后、重启后、导出再导入后均可逐字段读回。
- [x] 历史 prose-only proposal 可读取且不会伪造审核材料；标明缺失/旧格式。
- [x] 保留来源及 schema version；不得用包含作者文本的通用运行日志替代领域持久化。
- [x] 迁移失败不产生部分状态，备份表/列完整性测试覆盖新增载荷。

**验证要求**

新增 persistence/API/backup round-trip 测试；相关模型网关与迁移测试；compileall、Ruff。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

