# 顺序修复交接（2026-09-07）

用户要求按索引逐项处理，并遵守各 issue 前置依赖。本次续接完成前置 AUD-18，再完成 AUD-14、AUD-15。最新指令为“完成当前 AUD-15 就停止”，已遵守；本次经历一次自动上下文压缩，未进入第二次。未开始 AUD-16 的实现。再次获准继续时先读本文件、README.md、TRACKING.md 和下一项及其未完成前置 issue。

## 已完成：16 / 23

| Issue | 本地提交 | 结果 |
|---|---|---|
| AUD-09 | e064496 | CI 切换当前中文工作台 E2E |
| AUD-10 | 8ec9d04 | 恢复锁定版本 Ruff format 门禁，机械修改独立提交 |
| AUD-01 | cc9664c | 自动保存冻结快照与所属 scope |
| AUD-02 | 141af5a | 保存确认只更新请求快照的基线，保留期间修改和离开保护 |
| AUD-03 | bc7721e | Snowflake 接受版本检查与写入同一原子事务 |
| AUD-04 | da42ecf | 正文生成获得完整计划上下文，计划与已确认事实分离 |
| AUD-05 | f2109f9 | 持久化完整生成审核材料，迁移 13 |
| AUD-06 | 2f85481 | 展示审核材料及本机逐项处理状态 |
| AUD-07 | aa04289 | 场景来源映射与规划版本，迁移 14 |
| AUD-08 | df5fe65 | Step 8 回改生成更新提案、差异审核、冲突检查及正文过期提示，迁移 15 |
| AUD-11 | 365a5f4 | 叶子 context、正文/审核显式端口，解除 workspace/store 循环 |
| AUD-12 | 20ad9b7、3626351 | 两阶段拆分正文状态模块与雪花编辑区域；保留唯一会话所有权及薄门面 |
| AUD-13 | b25f40b | 服务显式依赖、应用异常与 HTTP 映射分离、Outbox 纯事件工厂 |
| AUD-18 | 83d85f5 | 事实/知识版本化更正、撤回与历史，知识隔离，迁移 16 和旧备份兼容 |
| AUD-14 | 7f8fbe0 | 前后端按领域拆分 DTO，兼容导出与关键输出契约一致性检查 |
| AUD-15 | 1775750 | 按聚合拆分事务、服务窄数据端口、统一写锁入口与并发/回滚验证 |

每项 issue 和 TRACKING.md 已更新。未推送远端，未创建 GitHub issues/PR。

## 下一步

本次任务已按用户要求停止。再次继续时，索引下一项为 **AUD-16**：正式正文编辑草稿和待审核草稿的选区求助契约；随后 AUD-17 应用/撤销建议。已阅读这两个 issue 及少量编辑器、reviews store 代码，尚未编写契约或实现。保留项目/场景/提案/版本及原文快照，不能让旧选区附着到新编辑器；AUD-16 不直接修改正文。

剩余 AUD-16、17、19、20、21、22、23，共 7 项。对应原始 issue 文件及 README.md、manifest.json、publish.ps1 仍为未跟踪文件，已保留，不是遗漏的实现变更。已完成 issue 的记录均纳入各自提交。项目代码没有未提交修改。

## 验证与实现要点

- AUD-08 后全量后端 310 项 unittest 通过；Ruff check/format 与 compileall 通过。所有数据库测试使用临时 SQLite。
- AUD-11 后前端 lint、build、33 项 Node + 73 项 Vitest 和 3 条 E2E 通过。浏览器门禁为 workspace-review、workspace-wiki-failure、scene-record-update。
- AUD-12 后前端 lint、build、30 项 Node + 81 项 Vitest 和 3 条 E2E 通过。减少了锁定源码位置的断言，新增 8 项实际装配/组件行为测试；递归依赖检查覆盖 stores 子目录。
- AUD-13 后后端 319 项 unittest、Ruff check、192 文件 format check、compileall 通过。全套首次发现旧接受接口失败时的弃用头丢失，已修复并经全套重跑确认。完整本机日志在忽略目录 `.tmp/aud13-backend.log`。
- AUD-18 后后端 331 项测试通过；新增 12 项 API、时态/知识隔离、并发、失败回滚与备份/迁移回归。事实更正后角色知识降为 planned，作者须重新确认；撤回使用 retracted，历史和 ID 保留。管理 UI 由 AUD-19 承接。[维护契约](../../narrative-maintenance-contract.md)。
- AUD-14 后后端 335 项测试、前端 31 项 Node + 81 项 Vitest、lint/build 通过；后端 110 个模型 schema 和完整 OpenAPI 拆分前后等值。这里的“模型”是 Pydantic 数据结构：109 个领域 DTO 类加 1 个兼容导入的 ManuscriptSceneDraftContract，不是 AI 模型；每个创建/更正/输出结构分别计数。提交的长期契约 fixture 仅选取 5 类关键输出。[DTO 边界](../../domain-dto-boundaries.md)。
- AUD-15 后后端 343 项测试、Ruff check、227 文件 format check、compileall 通过，日志 `.tmp/aud15-backend.log`。前端未在 AUD-14 后修改。事务函数位于 `app/data/transactions`，flows.py 仅兼容导出；故障注入测试须 patch 实际所属模块。写事务入口为 `SqliteUnitOfWork(write=True)`，包括恢复修订与接受回写。[事务/端口边界](../../data-transaction-boundaries.md)。
- AUD-09 的 Linux GitHub Actions 尚未远端执行；本地门禁已通过。未进行真实付费模型、长篇负载或真实作者数据验收。
- AUD-06 的逐项审核选择保存在本机草稿缓存，不包含在项目备份中；原始生成材料由后端持久化并包含在备份中。
- AUD-08 以已接受 record revision 和目标 plan_version 检查更新；更新保留原 scene ID 与正文历史。人工接受、保存或恢复正文会记录当时的规划版本。旧场景来源不作猜测性匹配。
- AUD-11 的 projectContext 是叶子 store，workspace 通过 storeToRefs 兼容原组件。manuscriptReviewPort 由 workspace 装配，独立编辑器可不装配审核面板；禁止恢复领域对 workspace 的反向导入。新依赖边界和独立装配测试可用于 AUD-12。
- AUD-12 的正文门面在单一 Pinia scope 中创建 `stores/manuscript/` 职责模块；不要另建镜像 store/保存标志。雪花旧文导入组件实例随工作区存活，通过内部 visible 控制 DOM，保留跨步骤选文。[职责说明](../../manuscript-state-boundaries.md)。
- AUD-13 的服务 HTTP 工厂统一从 `app.dependencies` 导入；核心服务不加载 FastAPI。应用异常由 `app.http_errors` 映射，带结构化 detail；旧接受路由附加弃用头时复用同一转换函数。数据事务引用 `app.outbox.events`；handlers 旧工厂名称仅 re-export。[边界说明](../../application-http-boundaries.md)。

## 本机执行

遵循根 AGENTS.md 和 `C:/Users/pzr/.codex/RTK.md`：PowerShell 7，命令经过 rtk，前端 pnpm，后端 uv。uv 默认缓存不可用，已改用项目 `.tmp/uv-cache`，不需安装新依赖。

```powershell
# 在 backend 目录
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev python -m unittest discover -s tests -q
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev ruff check app tests
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev ruff format --check app tests
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev python -m compileall -q app
# 在 frontend 目录，分别执行
rtk pnpm lint
rtk pnpm test
rtk pnpm build
rtk pnpm test:e2e
```

本地 Git 暂存/提交因 `.git` 权限需工具审批，本轮均已获自动审核通过；按 issue 独立提交。不要发布原始 issue 文件，除非用户另行授权。
