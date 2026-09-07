# 将 CI 浏览器门禁切换到当前中文工作台 E2E

处理状态：已修复并通过本地验证（2026-09-07）。CI 改为在 frontend 中执行 `pnpm test:e2e`，README 与 E2E 文档统一入口，保留 legacy 说明。Windows 实跑两条当前工作台 E2E 均通过；Linux 解释器路径与 Chromium 安装步骤已核对，未推送或触发 Actions，远端运行结果待 CI 验证。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

当前 pnpm test:e2e 的 workspace-review 和 workspace-wiki-failure 均通过；CI 仍运行 full-review-loop.e2e.mjs，实测在查找 Open project 英文按钮时等待 30 秒后失败。

**涉及位置**

- `.github/workflows/verify.yml:108`
- `frontend/package.json`
- `e2e/README.md`
- `README.md`

**修复边界**

统一 CI、package scripts 和开发文档的当前 E2E 入口；历史脚本保留时明确标为 legacy，不纳入当前发布门禁。不要通过跳过浏览器测试或放宽断言恢复绿灯。

**验收标准**

- [x] CI 执行与 pnpm test:e2e 相同的当前工作台用例。
- [x] 故障重试和真实 SQLite 数据隔离仍被测试，临时进程正确清理。
- [ ] Linux CI 的 Python 路径和 Chromium 安装有效，记录实际运行结果。
- [x] README/e2e 文档无相互矛盾的首选命令。

**验证要求**

pnpm test:e2e；可访问时核对更新后的实际 Actions 结果。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
