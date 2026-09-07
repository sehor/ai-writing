# 补齐三类作者场景的验收矩阵并同步完成状态文档

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / documentation。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

工程完成度缺口：README、旧整改计划、Snowflake completed 标记和实际 UI/CI 存在漂移。测试数通过不能替代 PRD 场景 A/B/C 的端到端证明。

**涉及位置**

- `README.md`
- `docs/ai-writing-remediation-plan.md`
- `docs/snowflake-business-loop-improvement-plan.md`
- `e2e/README.md`
- `e2e/workspace-review.e2e.mjs`
- `e2e/workspace-wiki-failure.e2e.mjs`

**修复边界**

建立需求→实现→行为测试→剩余限制的矩阵；补 A 结构化起草、B 选区求助及应用、C 保存分析与人工写回的当前工作台验收。同步入口、实际状态和未验证能力，归档历史结论但不抹去背景。

**验收标准**

- [x] 矩阵区分已实现、已验证、部分完成和后续范围；每项有可执行证据。
- [x] 三场景包含刷新/重启、冲突、失败重试及不会越过人工提交边界的断言。
- [x] 文档只在对应验收通过后标完成，不能复制旧 completed 或声称真实模型效果已验证。
- [x] 记录当前 CI 与本地测试结果，列出 P3 范围，不把可选项伪装成 MVP 阻断项。

**完成记录（2026-09-07）**

建立 [作者验收矩阵](../../author-acceptance-matrix.md)，按需求→实现→行为测试→限制映射A/B/C。新增 structured-drafting 浏览器用例，由UI创建章/场景、带完整计划生成、改稿/刷新/明确接受及后端正常重启保留。增强B的显式保存新修订及采纳状态独立断言，增强C的来源原文、接受前后权威边界、安全上下文更新和重启保留。

README、E2E说明、2026-08-31整改计划及Snowflake阶段计划同步；旧计划加历史日期，不能用旧Completed推广到全部产品。专用Redo/多候选选择器为部分完成；真实付费模型、外部CLP效果、远端Actions等仍未验证。AUD-22的999档卡顿及PERF-01/02为显式后续，不声称长篇性能已优化。

最终本机全量：364 backend unittest、Ruff check/format、compileall；33 Node +112 Vitest、lint/build、7条E2E均通过。2项文档/证据一致性检查验证矩阵路径及实际包命令；small性能入口和20/200/999独立测量已通过完整性断言（时延限制保留）。没有真实作者数据或付费调用，未推送/创建远端issues或PR。

**验证要求**

当前完整 E2E 和相关行为测试；人工核对文档命令及矩阵链接。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-06、AUD-08、AUD-09、AUD-10、AUD-17、AUD-19、AUD-20。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
