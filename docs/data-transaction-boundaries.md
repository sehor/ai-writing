# 数据端口与事务边界

`SQLiteWritingDataStore` 保留兼容门面，负责选择连接/Unit of Work 和转发。`WritingDataStore` 组合窄接口，并保留迁移、路由等旧调用者需要的其他操作；应用服务使用 `app/data/ports` 中的消费端 Protocol，不依赖整个门面。

Snowflake、正文、场景编译和回写事务分别位于 `app/data/transactions`；修订产生的四类 outbox 任务由 `revision_jobs` 统一安排。`app/data/flows.py` 仅保留显式兼容导出。事务函数接收同一连接，不自行连接、commit 或 rollback。

## 写入约定

需要读取当前状态/版本后做决定的审核、更正、正文编辑与恢复入口使用 `SqliteUnitOfWork(path, write=True)`。该入口在第一次业务读取之前执行 `BEGIN IMMEDIATE`；正常退出提交，异常退出回滚，启动失败也关闭连接。恢复修订和接受回写同样遵守此约定，避免两个调用者同时读到旧版本。

仅追加或单表操作仍可使用普通 Unit of Work。已有 `connect()` 和显式传 connection 的调用保持兼容，用于分析结果与提案的成批原子写入；参与者不能私自提交。不得将 provider 调用或外部文件操作放进长期写事务。

## 数据端口

读上下文拆为 ProjectSnapshotReader、NarrativeSnapshotReader 和 ReviewTargetReader；共享基础读取只定义一次。Manuscript/Snowflake/Compile/Writeback/Reference 服务各自组合所需读接口和修改方法。ModelService 仅需 GenerationRunReader；生成调用另用 GenerationRecorder。AnalysisDataPort 声明分析记录、回写提案和共用事务连接的契约。备份服务保留 SQLite 专用依赖，因为它需要真实数据库备份/恢复能力。

回归检查端口调用签名与 SQLite 门面相容；受限测试适配器只暴露声明的方法，运行实际快照流程。事务回归覆盖写锁在读取前取得、并发恢复版本、重复接受回写、故障注入回滚；既有雪花审核、场景更新、正文冲突、outbox 和备份全套继续作为验收门禁。
