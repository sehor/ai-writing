# 将 Snowflake 接受操作的版本检查纳入原子事务

处理状态：已完成（2026-09-07）。artifact 与 record 接受在读取候选/head 前取得 BEGIN IMMEDIATE 写事务；同候选重复接受返回原结果，不新增投影或 Outbox。新增独立连接/线程竞争、Outbox 失败全库回滚、幂等性测试（两类记录均覆盖）。Snowflake revision、compiler 路由、UnitOfWork 等 49 项测试通过，Ruff format/check、compileall 通过。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

已复现：两个候选使用相同旧 accepted head，两个线程同时完成 head 读取后继续执行，均返回 accepted，最终 head 被后一次写入覆盖。UnitOfWork 的进入没有启动写事务，SELECT 后才开始的隐式写事务无法保护先前检查。

**涉及位置**

- `backend/app/data/sqlite_store.py:260`
- `backend/app/data/flows.py:94`
- `backend/app/data/repositories/snowflake.py`
- `backend/app/data/repositories/snowflake_records.py`
- `backend/app/data/unit_of_work.py`

**修复边界**

修复 artifact acceptance 的读取、expected/base 检查、状态、head、投影、stale 和 Outbox 写入的原子性；同步核对 record decision 的同类不变量。记录式并发风险属于待核查范围，不把它未经复现地当成既定缺陷。

**验收标准**

- [x] 基于同一旧 head 的两个不同候选并发接受，只允许一个成功，另一个明确冲突。
- [x] 失败事务无 revision 状态、head、projection、stale 或 Outbox 部分提交。
- [x] 重复接受同一候选符合既有幂等约定，不制造额外投影或副作用。
- [x] 采用真实独立 SQLite 连接及并发请求测试；不能仅顺序调用或只检查源码中有 BEGIN。

**验证要求**

后端并发回归、test_snowflake_revisions、test_unit_of_work 和相关路由测试；compileall、Ruff。屏障不要放在正确实现必须串行获得的写锁之后。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

