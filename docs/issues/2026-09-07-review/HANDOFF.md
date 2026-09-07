# 顺序修复交接（2026-09-07）

用户本轮明确要求完成 AUD-20、21、22、23。已按依赖顺序完成并逐项本地提交，原23项在各自边界内全部验收。此处是最终交接，不再有下一项原AUD待办；更大产品愿景及未验证能力不能自动算作完成。

## 已完成：23 / 23

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
| AUD-16 | 8becb11 | 两类正文草稿选区求助、版本/会话隔离、结构化来源与迁移 17 |
| AUD-17 | 6bcd27c | 参考建议预览、替换/插入、重复保护和安全撤销只写现有本地草稿 |
| AUD-19 | cd915a2 | 时态事实/读者知识/角色知识作者界面、统一草稿安全与 scene-safe 预览/生成隔离 |
| AUD-20 | 4953825 | 真实分析执行范围/来源、未配置与有限检查提示、CLP证据校验、迁移18 |
| AUD-21 | d7ca277 | 卷/章节归属、非破坏删除与排序、旧备份兼容及迁移19 |
| AUD-22 | 51b6c38 | 20/200/999场景容量基线、完整性/超限验证与轻量CI，实测卡顿另列后续 |
| AUD-23 | 本提交（git log --grep=AUD-23） | A/B/C矩阵、7条真实浏览器流程、重启/人工边界证据与历史文档状态同步 |

每项 issue 和 TRACKING.md 已更新。未推送远端，未创建 GitHub issues/PR。

## 完成范围与后续

原23项无剩余待办。新后续优化见 [PERF-01/02](../../performance-followups.md)：999场景历史面板中位约5秒、最慢20秒，场景切换约845ms；完整性已通过不等于交互达标。专用多级Redo/结构化多候选选择仍为部分完成，详情见 [作者验收矩阵](../../author-acceptance-matrix.md)。真实付费模型/外部CLP效果、真实作者数据、生产性能、远端Linux Actions未验证，没有自动启动或发布这些工作。

AUD-20～23文档均随各自提交纳入跟踪。只保留本审查目录的原始 README.md、manifest.json、publish.ps1 未跟踪；未删除、未执行发布脚本，未推送远端或创建GitHub issues/PR。项目代码及本轮验收文档均已本地提交。

## 验证与实现要点

- **最终全量**：364项backend unittest；全backend Ruff check/format、app/scripts compileall；33项Node +112项Vitest、lint/build；7条当前中文工作台E2E通过。A/B/C新增断言覆盖UI建章/场景、本地草稿刷新、手动提交、来源证据、安全上下文更新及正常后端重启。专用Redo未冒充验证。
- AUD-20：execution_json记录每次Outbox处理器/范围，旧记录null不猜测。CLP未配置是not_executed，本地规则是limited，失败可重试；不会随保存自动启用Provider。CLP虚构引文被拒绝。[能力与可选效果方案](../../analysis-capabilities-and-acceptance.md)。
- AUD-21：卷与章节归属用独立表及复合外键，删卷只解归属不删正文，scene.sequence仍是叙事时点。schema≤18备份可导入，旧ID不变。[卷契约](../../manuscript-volume-contract.md)。
- AUD-22：20/200/999场景、每场景2,000字/3个修订均完成数据库、HTTP和浏览器分层测量；恢复哈希及数量一致，越界写入422。CI仅small，15秒宽松挂起保护不等于产品预算。一次全档调用触及工具300秒时限，之后大档独立完整通过；固定基线与限制见 [性能文档](../../performance-baseline.md)，原始测量在 `.tmp/performance-*.json`，不可把测试完成理解为大档已流畅。

以下为各阶段历史记录：

- AUD-08 后全量后端 310 项 unittest 通过；Ruff check/format 与 compileall 通过。所有数据库测试使用临时 SQLite。
- AUD-11 后前端 lint、build、33 项 Node + 73 项 Vitest 和 3 条 E2E 通过。浏览器门禁为 workspace-review、workspace-wiki-failure、scene-record-update。
- AUD-12 后前端 lint、build、30 项 Node + 81 项 Vitest 和 3 条 E2E 通过。减少了锁定源码位置的断言，新增 8 项实际装配/组件行为测试；递归依赖检查覆盖 stores 子目录。
- AUD-13 后后端 319 项 unittest、Ruff check、192 文件 format check、compileall 通过。全套首次发现旧接受接口失败时的弃用头丢失，已修复并经全套重跑确认。完整本机日志在忽略目录 `.tmp/aud13-backend.log`。
- AUD-18 后后端 331 项测试通过；新增 12 项 API、时态/知识隔离、并发、失败回滚与备份/迁移回归。事实更正后角色知识降为 planned，作者须重新确认；撤回使用 retracted，历史和 ID 保留。管理 UI 由 AUD-19 承接。[维护契约](../../narrative-maintenance-contract.md)。
- AUD-14 后后端 335 项测试、前端 31 项 Node + 81 项 Vitest、lint/build 通过；后端 110 个模型 schema 和完整 OpenAPI 拆分前后等值。这里的“模型”是 Pydantic 数据结构：109 个领域 DTO 类加 1 个兼容导入的 ManuscriptSceneDraftContract，不是 AI 模型；每个创建/更正/输出结构分别计数。提交的长期契约 fixture 仅选取 5 类关键输出。[DTO 边界](../../domain-dto-boundaries.md)。
- AUD-15 后后端 343 项测试、Ruff check、227 文件 format check、compileall 通过，日志 `.tmp/aud15-backend.log`。前端未在 AUD-14 后修改。事务函数位于 `app/data/transactions`，flows.py 仅兼容导出；故障注入测试须 patch 实际所属模块。写事务入口为 `SqliteUnitOfWork(write=True)`，包括恢复修订与接受回写。[事务/端口边界](../../data-transaction-boundaries.md)。
- AUD-16 后后端 350 项测试、Ruff check、228 文件 format check、compileall 通过；前端 31 项 Node + 90 项 Vitest、lint/build 和 4 条 E2E 通过。新增浏览器门禁 copilot-selection，覆盖两类草稿选区→建议且不自动保存正文。截图 `.tmp/copilot-selection.png` 已检查，完整日志 `.tmp/aud16-backend.log`。旧迁移测试的固定待迁移数已改为按实际迁移列表计算。
- AUD-16 的 `ReferenceEditorContext` 使用 UTF-16 码元偏移；来源随参考建议以可空 JSON 列保存，旧记录/备份为 null。后端检查项目、场景、提案状态和正文版本，允许本地未保存草稿；实际 prompt 使用有界上下文加完整选区。`CopilotEditor` 注册当前编辑会话，`copilotContext` 仅管理临时选区，不拥有保存或正文修改权。切换/修改后旧选区过期，旧异步结果不能激活到新编辑器。关键 schema fixture 已增至 6 类。[选区契约](../../copilot-selection-contract.md)。
- AUD-17 后前端 31 项 Node + 94 项 Vitest、lint/build 和 4 条 E2E 通过。新增 `referenceApplication` 只协调 proposalDraft/正式正文已有本地草稿；预览不写正文，应用触发既有 dirty/cache，不直接保存版本；应用后旧快照失效阻止重复插入，撤销仅在同会话/目标/版本且文本仍等于应用结果时允许。[选区与应用契约](../../copilot-selection-contract.md)。
- AUD-19 后前端 31 项 Node + 102 项 Vitest、lint/build 和 5 条 E2E 通过。Canon 现有导航复用 NarrativePanel 维护全部作者事实/知识；事实和知识 scope 接入统一 draftSessions。场景预览只读取 `/story-state`，新增浏览器 E2E 证明未来隐藏事实虽然在作者管理列表可见，但场景 4 预览和真实本地 Reference `used_context` 都不会泄漏该秘密；无外部/付费模型调用。截图 `.tmp/narrative-maintenance.png`。[作者界面契约](../../narrative-maintenance-ui.md)。
- AUD-09 的 Linux GitHub Actions 尚未远端执行；本地门禁已通过。真实付费模型和真实作者数据未验收；合成长篇负载测量已由AUD-22补齐，范围不外推。
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
rtk pnpm test:perf
# 更大性能测量按根目录单档执行，避免单工具时限：
# rtk proxy node e2e/longform-benchmark.mjs --size medium
# rtk proxy node e2e/longform-benchmark.mjs --size large
```

本地 Git 暂存/提交因 `.git` 权限需工具审批，本轮均已获自动审核通过；按 issue 独立提交。不要发布原始 issue 文件，除非用户另行授权。
