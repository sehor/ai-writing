# 把完整场景计划传入正文生成上下文

处理状态：已完成（2026-09-07）。统一 NarrativeSnapshot 上下文新增四项明确标记为作者计划的字段，空值显示 Not specified；正文、参考和编译路径共享该渲染器。FakeModelGateway 对四项独立标记逐一断言，并验证 Canon/StoryFact/正文不被生成操作改写。7 项 provider/narrative snapshot 边界测试、Ruff format/check、compileall 通过。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P1 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

已复现：在 outcome、information_delta、character_state_delta、story_thread_actions 中放入唯一标记，FakeModelGateway 捕获的实际 prompt 中四项均缺失。当前 snapshot 的场景部分只渲染 POV、goal、conflict、turning point 等旧字段。

**涉及位置**

- `backend/app/narrative/snapshot.py:174`
- `backend/app/services/manuscript_service.py:171`
- `backend/app/prompts/creative.py`
- `backend/app/agents/manuscript_workflow.py`

**修复边界**

将已保存的关键 SceneContract 计划字段纳入统一生成上下文，明确标为本场景计划而非已确认事实；审计使用该 snapshot 的正文及相关参考生成路径。

**验收标准**

- [x] 实际模型请求包含四项计划字段，逐项独立验证，不能只断言整个 snapshot 字符串相同。
- [x] 计划变化不能直接写入 Canon、StoryFact 或正文；仍需既有审核。
- [x] 原有 reader/POV/future spoiler 隔离测试通过，legacy open_threads 仍不重新成为权威输入。
- [x] 空字段处理明确且不会生成虚假的已确认状态。

**验证要求**

FakeModelGateway 捕获实际 prompt 的行为测试；provider_manuscript_snapshot_boundary、narrative_snapshot_boundary 等回归。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

