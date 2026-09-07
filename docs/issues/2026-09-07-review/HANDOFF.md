# 顺序修复交接（2026-09-07）

用户要求按索引逐项处理，并且本任务最多允许一次上下文压缩。目前已使用一次；在第二次压缩前主动停在完成节点。继续时先读本文件、README.md、TRACKING.md 和下一项 issue。不要再次压缩当前任务。

## 已完成：11 / 23

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

每项 issue 和 TRACKING.md 已更新。未推送远端，未创建 GitHub issues/PR。

## 下一步

从 AUD-12 开始，其 AUD-06/08/11 前置均完成。已阅读 AUD-12，尚未修改实现：按职责逐步拆分 manuscript store、Snowflake 编辑组件，保留薄门面，交付职责/依赖说明。注意该任务要求分阶段提交，不要仅搬动共享 refs 或复制会话标志。

AUD-13 至 AUD-23 尚未处理；继续遵守各 issue 的前置依赖，特别是共享模型/迁移的串行修改。原始 AUD-12 至 AUD-23、README.md、manifest.json、publish.ps1 仍为未跟踪文件，已保留，不是本轮遗漏的代码变更。项目代码没有未提交修改。

## 验证与实现要点

- AUD-08 后全量后端 310 项 unittest 通过；Ruff check/format 与 compileall 通过。所有数据库测试使用临时 SQLite。
- AUD-11 后前端 lint、build、33 项 Node + 73 项 Vitest 和 3 条 E2E 通过。浏览器门禁为 workspace-review、workspace-wiki-failure、scene-record-update。
- AUD-09 的 Linux GitHub Actions 尚未远端执行；本地门禁已通过。未进行真实付费模型、长篇负载或真实作者数据验收。
- AUD-06 的逐项审核选择保存在本机草稿缓存，不包含在项目备份中；原始生成材料由后端持久化并包含在备份中。
- AUD-08 以已接受 record revision 和目标 plan_version 检查更新；更新保留原 scene ID 与正文历史。人工接受、保存或恢复正文会记录当时的规划版本。旧场景来源不作猜测性匹配。
- AUD-11 的 projectContext 是叶子 store，workspace 通过 storeToRefs 兼容原组件。manuscriptReviewPort 由 workspace 装配，独立编辑器可不装配审核面板；禁止恢复领域对 workspace 的反向导入。新依赖边界和独立装配测试可用于 AUD-12。

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
```

本地 Git 暂存/提交因 `.git` 权限需工具审批，本轮均已获自动审核通过；按 issue 独立提交。不要发布原始 issue 文件，除非用户另行授权。
