# 恢复后端 Ruff format 门禁

处理状态：已完成（2026-09-07）。使用锁定 Ruff 0.16.4 格式化 37 个文件，未修改规则或依赖。`ruff format --check .`（185 files already formatted）、`ruff check .`、`python -m compileall -q app` 和全量 unittest（297 项）通过，均通过 `uv run --frozen --extra dev` 执行；受限环境设置项目临时 UV_CACHE_DIR。

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / bug。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

审查基线执行 ruff format --check . 失败：37 files would be reformatted，148 files already formatted；ruff check 单独通过。CI 将 format 检查作为必跑步骤。

**涉及位置**

- `backend/app/`
- `backend/tests/`
- `backend/scripts/`
- `backend/pyproject.toml`
- `.github/workflows/verify.yml:35`

**修复边界**

使用仓库锁定的 Ruff 版本做机械格式化，单独提交并保持逻辑不变。不放宽规则、不升级工具版本。

**验收标准**

- [x] 与 CI 等价的 Ruff format --check 返回 0。
- [x] ruff check、compileall、后端测试通过。
- [x] 差异只有格式变化，报告格式化文件数量。

**验证要求**

uv run --frozen --extra dev ruff format --check .；ruff check .；python -m compileall -q app；python -m unittest discover -s tests。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

无任务前置，可按文件冲突情况独立开展。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。
