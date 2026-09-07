# 补齐卷层级与既有章节场景的兼容组织

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P3 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

完成度缺口：PRD/产品说明包含卷、章、场景；当前实现主要组织单元为章和场景。卷层级属于后续产品补齐，不阻断当前数据安全修复。

**涉及位置**

- `backend/app/models.py`
- `backend/app/data/repositories/manuscript.py`
- `backend/app/data/migrations.py`
- `backend/app/routers/manuscript.py`
- `backend/app/manuscript_export.py`
- `frontend/src/components/ManuscriptWorkspace.vue`
- `frontend/src/stores/manuscript.ts`

**修复边界**

先确定卷归属和排序的最小设计，再增加卷的创建/重命名/排序、章节归卷、目录和导出。旧项目保留未分卷章节，不强制迁移作者结构。

**验收标准**

- [x] 旧数据库无损升级，章节/scene/revision ID 保持不变。
- [x] 删除卷不会隐式删除章、场景或正文；归属迁移明确。
- [x] 跨卷章节和导出顺序稳定，备份恢复保留组织关系。
- [x] 空卷、未分卷、移动章节和项目切换有可用交互。

**完成记录（2026-09-07）**

迁移19新增可选卷与独立章节归属；创建、更名、排序、归卷、删除、目录及导出完成。删除卷只解除归属，旧ID、叙事时点及正文历史保持。使用现有 manuscript 单一会话与统一草稿安全，不新增镜像 store。

后端360项、前端31 Node +112 Vitest、Ruff/compileall、lint/build及6条E2E通过。新增5项后端、6项前端测试与卷浏览器流程；截图已检查。备份兼容≤18及旧来源/知识历史测试通过。见 [卷组织契约](../../manuscript-volume-contract.md)。

**验证要求**

迁移/备份/导出测试与卷→章→场景浏览器流程；不把多窗口协作等新能力并入本 issue。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-08、AUD-12、AUD-14。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

