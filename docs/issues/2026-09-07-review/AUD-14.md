# 按领域拆分前后端共享 DTO 并收紧契约一致性检查

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

结构观察：backend/app/models.py 1,220 行；frontend/src/types/index.ts 620 行。修改一个领域会触及全局契约文件，新字段易出现存储/API/UI 漏传。

**涉及位置**

- `backend/app/models.py`
- `frontend/src/types/index.ts`
- `backend/app/snowflake/contracts.py`
- `backend/tests/test_architecture_boundaries.py`
- `frontend/tests/`

**修复边界**

按 project、snowflake、canon/narrative、manuscript/review、analysis/model 等边界拆分；保留兼容导出并建立少量关键 API 的结构一致性/round-trip 校验。不新增大型代码生成依赖。

**验收标准**

- [x] 领域模型单向依赖清晰，没有把全局 models 文件复制成多个相互导入文件。
- [x] 兼容导入、OpenAPI、序列化、旧备份保持兼容。
- [x] 新增字段通过真实 API/持久化 round-trip 验证，前端关键字段有实际消费测试。

**完成记录（2026-09-07）**

前后端 DTO 分为 13 个领域模块，原入口保留显式兼容导出。后端 110 个模型 schema 和完整 OpenAPI 拆分前后等值；架构测试检查循环与基础设施依赖。补齐前端事实/知识/历史类型，增加 5 个关键输出 schema 的后端新鲜度和前端 TypeScript 结构检查，无新增依赖。

叙事维护真实 API/重开数据库测试和既有正文审核、场景来源、备份及前端组件行为回归通过。全量后端 335 项测试、Ruff/211 文件格式/compileall；前端 31 项 Node 检查 + 81 项 Vitest、lint/build 通过。边界与刷新命令见 `docs/domain-dto-boundaries.md`。

**验证要求**

后端模型/API/备份回归和 frontend 类型构建；相关行为测试。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-05、AUD-07、AUD-18。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
