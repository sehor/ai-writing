# 保存分析能力与验收（AUD-20，2026-09-07）

## 执行契约

保存正文/接受提案先提交权威正文与 Outbox，再由 dispatcher 执行派生工作。失败不会撤销正文，也不会直接写 Canon。沿用 pending/processing/succeeded/failed 调度状态，新增 `OutboxJob.execution` 表示**该次完成的执行**，不能用任务成功代替能力认证。

| 路径 | 实际能力 | 不代表什么 |
|---|---|---|
| consistency_analysis | local_rules，本地文本/启发式规则，limited | 零 findings 不是完整语义无矛盾 |
| writeback_analysis | local_cognition，本地候选，limited | 不会自动调用 Provider 或采纳候选 |
| clp_extraction 未配置 | not_configured / not_executed | 空候选不是外部模型检查成功 |
| CLP 已配置 | external_clp，有来源候选 | 仍须人工审核，效果未认证 |
| CLP 无效配置或处理器异常 | unavailable 或实际 mode / failed | 不会静默伪装成成功的本地降级 |
| llm_wiki_ingest | 实际 Wiki 类名 / index | 索引不是审稿 |
| 手动 Provider | 仅作者主动调用；runtime 可修复/降级并记录 generation_runs/attempts | 保存不会自动开启付费请求，运行成功不代表文学/语义效果已验证 |

迁移 18 增加 `outbox_jobs.execution_json`，旧记录/旧备份默认 null，界面显示执行范围未知，不推测历史配置。完成状态和 evidence 同次写入；重试清空上次结果，重新记录实际处理器。保留来源 source_ref，不保存凭证。`semantic_review` 恒为 false，因为当前处理器没有完整语义审稿承诺。

CLP HTTP 适配器验证结构、身份、版本、来源，并要求 evidence.excerpt 非空且实际出现在指定 revision 原文中；不接受只有正确 source_ref 的虚构引文。

## 确定性证据

`backend/tests/test_analysis_capabilities.py`：未配置、有限规则、配置失败、重开与备份恢复、虚构引文拒绝（5 项）。

`test_clp_sidecar.py`：合法/畸形响应、超时/网络错误、来源身份、失败重试、零候选缓存、重复处理去重、只有人工接受才写入关系/故事线。

`test_model_runtime.py`、`test_model_gateway_workflows.py`：Fake 超时、JSON 修复、降级、认证失败不降级、调用记录与候选边界。`test_authoring_failure_isolation.py`、`test_post_accept_analysis.py`、`test_outbox_dispatcher.py` 验证保存/派生故障隔离。

`frontend/tests/analysis-capabilities.test.ts`（4 项）与 `e2e/workspace-wiki-failure.e2e.mjs` 断言真实 UI 的未配置/未执行/有限检查/失败及重试，不再把 disabled CLP 显示为完整检查。

本轮本机：后端 355 unittest；前端 31 Node + 106 Vitest；lint/build；5 条 E2E 通过。数据为临时 SQLite/合成小说，无真实付费调用。

## 可选真实模型效果验收方案（未执行）

须由作者明确授权模型、预算及可发送文本后执行；默认不启用。使用至少 30 个脱敏合成片段，均附人工标准答案：已知事实冲突、人物未知秘密、未来揭示、无冲突对照各一组；相同冻结正文与已确认上下文在所选模型/CLP版本各跑 3 次。

记录日期、模型配置ID/版本、prompt版本、来源revision、修复/降级/耗时/费用、候选与引文、两位作者独立判断及分歧。报告准确率/召回率、虚构证据数、未来信息泄漏数、无害文本误报率及重试重复候选数；文学质量单独评分，不混入契约通过率。任何泄漏或未审核写入均阻断该配置验收；其他阈值在试验前由作者签定，不事后降低标准。

执行记录：**未执行，未获真实付费模型/真实作者文本验收授权**。当前完成的是能力说明、可靠性及人工边界的离线验收，不是实际模型效果认证。
