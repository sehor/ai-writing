# 作者场景验收矩阵（AUD-23）

核对日期：2026-09-07。需求来源为 [2026-08-31整改计划的三类场景](./ai-writing-remediation-plan.md)；该旧计划保留历史背景，不直接代表当前状态。当前整改记录见 [TRACKING](./issues/2026-09-07-review/TRACKING.md)。本矩阵以实际动作/持久化结果为证据，不用测试总数代替用户故事。

状态词：**已实现/已验证**指下面列出的本地路径及断言成立；**部分完成**明确原始愿景中未覆盖的交互；**已实现/受控验证**指Fake或可控sidecar证明契约，不代表真实模型效果；**后续范围/未验证**不冒充已完成。

## 场景 A：结构化起草

| 需求 → 实现 | 状态 | 可执行证据与关键断言 | 剩余限制 |
|---|---|---|---|
| 项目→章→Scene Contract→草稿：ManuscriptInputs、manuscript structure模块、ManuscriptService | 已实现/已验证 | [structured-drafting.e2e.mjs](../e2e/structured-drafting.e2e.mjs)：项目经真实API准备，章/场景通过UI创建；界面本地生成请求包含outcome、information_delta、character_state_delta；生成后无正式正文 | 该用例不宣称项目创建UI或实际付费生成效果已端到端验证；项目选择为真实界面 |
| 草稿可编辑且保留AI原稿，审核材料可逐项处理：proposalDraft、GenerationReview | 已实现/已验证 | [workspace-review.e2e.mjs](../e2e/workspace-review.e2e.mjs)：真实生成服务+受控Fake创建完整材料，浏览器审核选择刷新后恢复；[generation-review.test.ts](../frontend/tests/generation-review.test.ts)、[test_manuscript_generation_review.py](../backend/tests/test_manuscript_generation_review.py) | Fake验证结构/持久化，不证明文学质量；本机逐项处理状态不随项目备份迁移，原始审核材料会备份 |
| 本地草稿刷新恢复，手动接受才创建正式修订，重启后可读 | 已实现/已验证 | [structured-drafting.e2e.mjs](../e2e/structured-drafting.e2e.mjs)：Ctrl+S仅暂存未审核草稿；刷新保留作者修改；接受后v1；关页、正常停止并重启后端、重开UI，正文/scene/revision ID不变 | 正常重启不是模拟断电；崩溃恢复另由 [test_backup_recovery.py](../backend/tests/test_backup_recovery.py) 验证 |
| Step8回改→更新提案→人工审核→稳定来源与冲突检测 | 已实现/已验证 | [scene-record-update.e2e.mjs](../e2e/scene-record-update.e2e.mjs)、[test_scene_record_updates.py](../backend/tests/test_scene_record_updates.py)、[test_snowflake_acceptance_concurrency.py](../backend/tests/test_snowflake_acceptance_concurrency.py)：拒绝过期接受、保留场景/正文历史、提示规划已更新 | 规划变更不自动重写已保存正文，旧无来源场景不猜测匹配 |

## 场景 B：Copilot 辅助

| 需求 → 实现 | 状态 | 可执行证据与关键断言 | 剩余限制 |
| 两类草稿选区/整场景+作者问题→有来源建议：CopilotEditor、copilotContext、ReferenceService | 已实现/已验证 | [copilot-selection.e2e.mjs](../e2e/copilot-selection.e2e.mjs)、[copilot-selection.test.ts](../frontend/tests/copilot-selection.test.ts)、[test_reference_selection.py](../backend/tests/test_reference_selection.py)：中文/emoji UTF-16选区、冻结正文与来源；旧异步结果不能附着新编辑器 | 刷新/新会话后旧选区须重新捕获；不是持久化可重放的编辑命令 |
| 整理明确应用文本→预览→插入/替换→安全撤销：referenceApplication进入既有草稿状态 | 已实现/已验证 | [reference-application.test.ts](../frontend/tests/reference-application.test.ts)：目标/原文/版本/会话冲突、插入、重复点击、撤销保护；[copilot-selection.e2e.mjs](../e2e/copilot-selection.e2e.mjs)：两类草稿预览不修改、应用不提交、撤销恢复原文 | 建议可能是说明/多个方案，须作者选取或整理待应用正文，不能整段盲写 |
| 应用后显式保存→新修订→刷新持久化，采纳状态与正文编辑独立 | 已实现/已验证 | [copilot-selection.e2e.mjs](../e2e/copilot-selection.e2e.mjs)：撤销后重新预览/应用；未保存前仍1个修订；Ctrl+S后v2且刷新保留；参考建议仍pending_review | 重新应用是作者新的动作，**不是专用Redo栈**；保存后不使用旧会话撤销正式版本 |
| 原始愿景中的专用Undo/Redo栈、多候选结构化选择器 | 部分完成 / 后续范围 | 当前 [referenceApplication.ts](../frontend/src/stores/referenceApplication.ts) 提供单次受保护Undo和显式重新应用；无Redo公开动作。此行以实现边界为证据，不勾成完整实现 | 多级Redo和候选独立卡片不在AUD-17要求的应用/预览/撤销范围内，保留为后续交互增强；不以浏览器原生Ctrl+Y代替验收 |

## 场景 C：保存分析与人工写回

| 需求 → 实现 | 状态 | 可执行证据与关键断言 | 剩余限制 |
| 正文先提交→派生任务，界面显示实际能力：Outbox、AnalysisExecution | 已实现/已验证 | [workspace-review.e2e.mjs](../e2e/workspace-review.e2e.mjs)、[workspace-wiki-failure.e2e.mjs](../e2e/workspace-wiki-failure.e2e.mjs)：规则为有限检查；CLP未配置明确未执行，不拿调度succeeded冒充模型审稿；[test_analysis_capabilities.py](../backend/tests/test_analysis_capabilities.py) | 无findings不等于完整语义无矛盾，Provider不随保存自动调用；详见 [能力契约](./analysis-capabilities-and-acceptance.md) |
| 查看来源证据→人工接受→Canon更新→新场景安全上下文 | 已实现/已验证 | [workspace-review.e2e.mjs](../e2e/workspace-review.e2e.mjs)：经真实API准备一个有revision来源的待审候选，浏览器显示原文；接受前无目标Canon，点击后有且唯一；新Reference生成上下文读取已确认非时态约束，同时排除旧current_state；后端重启保留正文/修订/Canon | 该候选为可控验收夹具，不伪装成CLP实际抽取质量；不能以Canon摘要代替时态知识证据 |
| 失败隔离与重试、旧版本不覆盖当前作品 | 已实现/已验证 | [workspace-wiki-failure.e2e.mjs](../e2e/workspace-wiki-failure.e2e.mjs)：阻塞模块存储导致失败，UI重试恢复，不增加正文版本；[workspace-review.e2e.mjs](../e2e/workspace-review.e2e.mjs) 验证并发409后核对/保存；[manuscript-conflicts.test.ts](../frontend/tests/manuscript-conflicts.test.ts)、[test_authoring_failure_isolation.py](../backend/tests/test_authoring_failure_isolation.py) | 重试不是重新接受正文；部署环境失败和真实sidecar运维未测 |
| CLP合法/畸形/超时/来源证据/重试去重，Relation/Thread人工落地 | 已实现/受控验证 | [test_clp_sidecar.py](../backend/tests/test_clp_sidecar.py)、[test_model_runtime.py](../backend/tests/test_model_runtime.py)、[narrative-review.test.ts](../frontend/tests/narrative-review.test.ts)：可控HTTP/Fake和组件验证；虚构引文由 [test_analysis_capabilities.py](../backend/tests/test_analysis_capabilities.py) 拒绝 | 不声称真实CLP服务/实际模型抽取端到端效果通过，Relation/Thread这一路未额外运行真实外部sidecar浏览器用例 |
| 事实/读者/角色知识维护→按场景预览→未来信息隔离 | 已实现/已验证 | [narrative-maintenance.e2e.mjs](../e2e/narrative-maintenance.e2e.mjs)、[test_narrative_maintenance.py](../backend/tests/test_narrative_maintenance.py)、[test_provider_manuscript_snapshot_boundary.py](../backend/tests/test_provider_manuscript_snapshot_boundary.py)：UI更正、版本/草稿恢复、三栏预览，当前Reference和受控Provider正文上下文排除不可见事实 | 管理视图可以看未来真相，不因此把管理列表塞进生成上下文 |

## P3与未验证能力

卷层级（AUD-21）已实现并验证：[manuscript-volumes.e2e.mjs](../e2e/manuscript-volumes.e2e.mjs)、[test_manuscript_volumes.py](../backend/tests/test_manuscript_volumes.py) 证明归卷、稳定导出、旧备份恢复、删卷不删正文。它是组织能力，不更改故事时点。

性能测量（AUD-22）与 2026-09-08 的后续优化分别有证据：[原始基线](./performance-baseline.md)、[最新修复结果](./issues/2026-09-07-review/FIX-RESULT-2026-09-08.md)。20/200/999 档均验证完整性及超限错误；当前 999 档历史面板中位 214ms、场景切换 80ms、项目往返 1.46 秒，满足 [PERF-01/02](./performance-followups.md) 的同机预算。历史前端分页、按需渲染与跨页版本选择已实现；服务端分页、长时间内存与更多历史/附件仍属后续范围。

实际付费模型/真实CLP效果、真实作者项目验收、生产构建性能、Linux远端Actions尚未验证。可选模型效果方案及未执行记录见 [analysis-capabilities-and-acceptance.md](./analysis-capabilities-and-acceptance.md)。高级图形化、完整Redo栈和多作者协作没有本轮完成承诺。

## 可执行门禁与证据口径

**2026-09-08 更新：** P1 接受响应隔离、离开三选项和 P2 缓存撤回已补修。364 后端测试、33 Node＋125 Vitest、lint/build、完整 7 条 E2E 与 Step 8 额外连续 5 次通过；三档性能结果及新增回归见 [修复结果](./issues/2026-09-07-review/FIX-RESULT-2026-09-08.md)。以下保留前一日的验收记录。

**最终本机验收记录（2026-09-07）：** backend全量364项unittest通过；全backend Ruff check/format及app/scripts compileall通过。前端33项Node检查+112项Vitest、lint、生产build及当前7条真实E2E全部通过。`pnpm test:perf` small入口通过，三档固定性能测量与其慢项见上文。无真实付费调用、无真实作者数据；没有远端Actions执行结果。

当前 `frontend/package.json` 的 `test:e2e` 串行运行上面的7条当前中文工作台用例；`test:perf` 只跑small，完整性能按独立档运行。旧英文选择器脚本仅为legacy，不是当前CI入口。具体命令及夹具说明见 [e2e/README](../e2e/README.md)；依赖与全量检查见 [项目README](../README.md)。

[acceptance-evidence.test.mjs](../frontend/tests/acceptance-evidence.test.mjs) 验证本矩阵的相对证据链接、当前7条E2E包命令和固定性能结果结构，不能替代这些行为测试实际运行。跨平台执行尚需远端证据，不能因为工作流文件存在就说GitHub Actions已经通过。
