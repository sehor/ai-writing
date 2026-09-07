# 把 FastAPI 装配与异常映射移出后端应用服务

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

结构观察：多个 service 直接使用 Depends/HTTPException；writeback_service 导入 app.analysis.http；data flows 从 outbox.handlers 导入 payload 工厂。应用与 HTTP/执行层仍有反向耦合。

**涉及位置**

- `backend/app/services/manuscript_service.py`
- `backend/app/services/writeback_service.py`
- `backend/app/services/reference_service.py`
- `backend/app/services/compile_service.py`
- `backend/app/review/service.py`
- `backend/app/analysis/http.py`
- `backend/app/dependencies.py`
- `backend/app/routers/`
- `backend/app/outbox/handlers.py`

**修复边界**

服务显式接收依赖并抛领域/应用异常；HTTP 状态映射与 Depends 工厂归 router/dependency 层。事件 payload 类型/纯工厂放无运行依赖的叶子模块。保持现有 HTTP 契约。

**验收标准**

- [x] 服务核心不依赖 FastAPI HTTP 对象，可由 CLI、Outbox 和单元测试直接调用。
- [x] 404/409/422/502 等现有响应和结构化错误细节不变。
- [x] 事件契约不反向依赖 handler 的运行装配；无新增循环导入。
- [x] 保留兼容入口时集中 re-export，避免两份实现。

**验证要求**

架构边界、路由契约、故障隔离、Outbox 及直接 service 测试；compileall、Ruff、后端全套。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-04、AUD-05。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

## 完成记录（2026-09-07）

- 正文/编译服务显式接收依赖，所有 services 内 HTTP 工厂移至 `app.dependencies`；writeback 不再导入 `analysis.http`。
- `app.errors` 表达记录缺失、冲突、校验及模型配置/执行失败；`app.http_errors` 统一转换。保持 404/409/422/501/502 和一致性报告 detail，旧接受接口失败时的弃用响应头亦保留。
- `app.outbox.events` 持有纯 payload 工厂，事务流程直接引用；handlers 和 analysis 旧入口使用同一对象的 re-export。
- 新增 9 项直接服务、HTTP 契约、独立进程导入及兼容对象身份回归。后端全量 319 项 unittest 通过；Ruff check、192 文件 format check、compileall 通过。
- [依赖与异常职责说明](../../application-http-boundaries.md)。未改数据库/备份格式或模型业务规则；未执行真实付费 Provider 验收。
