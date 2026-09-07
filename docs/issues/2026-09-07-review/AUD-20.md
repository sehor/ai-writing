# 明确保存分析的处理器能力与降级状态并补齐 Provider/CLP 验收

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

完成度/验证缺口：默认一致性检查是本地文本规则，保存后的 writeback 走本地 cognition。已有任务/重试并不证明完整语义冲突检测；真实 Provider/CLP 效果本次未验证。

**涉及位置**

- `backend/app/outbox/handlers.py`
- `backend/app/analysis/consistency.py`
- `backend/app/integrations/knowledge_compiler.py`
- `backend/app/integrations/llmwiki_clp.py`
- `frontend/src/stores/analysisJobs.ts`
- `frontend/src/components/manuscript/WritebackReview.vue`

**修复边界**

先盘点已配置的处理器及能力契约，在 UI 区分本地规则、模型/外部分析、未配置、降级、失败；为现有 Provider/CLP 路径补确定性验收。不默认新增“完整语义审稿”承诺，也不自动启用付费调用。

**验收标准**

- [x] 作者知道执行了哪种检查、哪些未执行，不能把无 findings 等同于全语义无矛盾。
- [x] 使用 Fake/可控 sidecar 测试合法结果、畸形结果、超时、重试和来源证据；失败不阻断保存也不直接写 Canon。
- [x] 输出候选经人工审核才能落地，重复任务不重复产生已应用结果。
- [x] 形成真实模型效果验收方案与可选执行记录；未执行部分明确保留为未验证。

**完成记录（2026-09-07）**

迁移18持久化每次 Outbox 执行的处理器/范围；未配置 CLP 明确未执行，规则成功明确有限检查，旧任务不猜测历史配置。界面展示来源和限制，保留失败重试与人工提交边界。CLP 拒绝不在指定正文中的虚构证据引文。

后端 355 项、前端 31 Node + 106 Vitest、lint/build、5 条 E2E 通过；新增 5 项后端、4 项组件回归。真实模型效果仍未执行；方案和证据见 [能力契约](../../analysis-capabilities-and-acceptance.md)。

**验证要求**

现有 Outbox、CLP、故障隔离测试及 UI 状态测试；默认离线。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-05、AUD-06。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

