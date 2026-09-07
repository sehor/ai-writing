# 按聚合拆分事务流程并缩小数据端口依赖

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P3 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

结构观察：sqlite_store.py 993 行、flows.py 823 行、WritingDataStore 接口约 497 行。大门面本身不必删除，但不同领域事务和调用者依赖仍集中。

**涉及位置**

- `backend/app/data/flows.py`
- `backend/app/data/sqlite_store.py`
- `backend/app/data/interfaces.py`
- `backend/app/data/unit_of_work.py`
- `backend/app/services/`

**修复边界**

将 snowflake、manuscript、scene compile、writeback 的事务流程按业务职责拆分；需要时为应用服务定义窄 Protocol，保留兼容 facade。不要引入通用 CRUD 框架或改换数据库。

**验收标准**

- [x] 事务边界有统一且可执行的约定，跨表原子性不因文件拆分丢失。
- [x] 服务仅依赖所需数据操作，门面转发不包含新增业务逻辑。
- [x] 并发、幂等、失败回滚及备份恢复回归不退化。

**完成记录（2026-09-07）**

事务拆至 `app/data/transactions` 的 Snowflake、manuscript、scene_compile、writeback 及共用 revision_jobs，flows.py 保留兼容导出。`SqliteUnitOfWork(write=True)` 统一在状态/版本读取前取得写锁，应用到既有审核/更正入口及恢复修订、接受回写。跨表写入和 outbox 仍由同一个事务提交或回滚。

服务改为消费 `app/data/ports` 的窄 Protocol，WritingDataStore 组合这些接口并保留旧门面；共用读取与生成记录接口可复用。新增 8 项测试覆盖写锁、并发恢复、重复接受、故障回滚、受限读取适配器和端口签名。全量后端 343 项测试（含 review/outbox/备份恢复）、Ruff check、227 文件 format check、compileall 通过。详见 `docs/data-transaction-boundaries.md`。

**验证要求**

test_unit_of_work、review/state-machine、outbox、R3/R6 回归及后端全套。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-03、AUD-08、AUD-13、AUD-14。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
