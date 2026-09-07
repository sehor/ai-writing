# 提供时态事实、读者知识和角色知识管理界面

审查基线：本地提交 `7147ba58a135fd5a4a258e9ccb5b1d826acdf389`（2026-09-07）。创建 issue 时该提交尚未在 origin 查询到；下列位置为该本地基线的仓库相对路径。请在修复窗口核对当前分支，不要为了匹配旧行号回退他人修改。

**优先级 / 类型**：P2 / enhancement。本任务只负责下述范围；不包含其他 issue 的整片重构。

**问题与证据**

完成度缺口：后端存在 story-facts、story-state、character-knowledge 能力，但当前前端没有对应调用，普通作者无法维护 scene-safe snapshot 所需的完整数据。

**涉及位置**

- `frontend/src/components/NarrativePanel.vue`
- `frontend/src/components/CanonWorkspace.vue`
- `frontend/src/stores/narrative.ts`
- `frontend/src/types/`
- `frontend/src/api/`

**修复边界**

提供事实列表/详情、有效场景范围、读者可见时点、角色知情时点及更正入口；增加按场景/角色预览视图。沿用现有导航，不另建一套事实系统。

**验收标准**

- [x] 作者无需直接调用 API 即可创建、查看、更正事实和维护知情范围。
- [x] 同一场景下世界真相、读者已知、当前角色已知可对照，显示来源和保存状态。
- [x] 未来/隐藏信息仅在作者管理视图可见，不能因此进入正文生成安全上下文。
- [x] 项目切换、空状态、失败重试、草稿恢复及无效场景范围均有明确行为。

**完成记录（2026-09-07）**

在现有 Narrative store 上补齐 `story-facts`、knowledge-states、history 与 `story-state` 前端能力；Canon 的既有“故事设定”页面直接复用 `NarrativePanel mode="maintenance"`，Graph 保留完整叙事模式，没有新增顶层导航或第二套事实权威。作者可以从界面创建/版本化更正/撤回事实，维护读者与角色知情时点；world truth 显式只读并由事实派生。事实/知识表单都有来源、版本、保存/失败状态、范围校验和更正原因。

事实与知识编辑 scope 接入统一 draftSessions：400ms 本地缓存、记录切换 guard、项目切换汇总和 beforeunload flush 都沿用现有草稿安全路径；新建事实表单在项目 reset 时即建立 baseline，已有记录草稿在重新选择对应记录时恢复。API 失败可重试，成功的上一次 `story-state` 安全预览不会被失败请求清空，409/422 不静默覆盖或接受无效时间范围。

同场景预览只读取后端 `/story-state`，分别展示世界真相、读者已知和指定角色已知及来源/版本；不会从作者管理列表自行拼装未来或隐藏事实。新增真实浏览器 E2E 使用临时 SQLite，经界面创建当前事实、角色知识和未来隐藏事实，确认场景 4 预览不含未来秘密，并调用真实本地 Reference 生成证明 `used_context` 同样不泄漏该秘密；随后从界面更正事实到 v2。未调用外部/付费模型。

验证：31 项 Node + 102 项 Vitest（共 133 项前端检查/测试）、ESLint、生产 build 与 5 条 E2E 全部通过。专项为 6 项 Pinia + 2 项组件测试以及 `narrative-maintenance.e2e.mjs`。实现契约见 `docs/narrative-maintenance-ui.md`，截图生成于 `.tmp/narrative-maintenance.png`。

**验证要求**

组件/Pinia 及事实维护→场景预览→生成隔离的端到端测试。

执行命令遵循仓库 AGENTS.md：Windows/PowerShell，命令通过 rtk，前端 pnpm，后端 uv。使用临时数据库/合成文本，勿覆盖作者实际数据。

**依赖与协作**

前置任务：AUD-01、AUD-02、AUD-18。

不要同时修改其他窗口正在处理的相同文件；保留他人修改。开始前复核依赖 issue 是否关闭，完成后说明改动、验证、兼容性及剩余限制。

