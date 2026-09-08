# P1、P2 与长篇性能修复结果

日期：2026-09-08。实现提交：`8686160`。对应 [修复计划](./FIX-PLAN-2026-09-08.md) 与 [复核发现](./RECHECK-2026-09-08.md)。本轮修复和本机验收已完成。共享草稿与 workspace 装配改动合为一个实现提交，测量和文档另行提交。

## 草稿安全

- P1：离开有修改的正文提案时，可选择保存草稿并离开、不保存并离开或取消。保存仅进入本机缓存；放弃会清理缓存、取消定时器并重置草稿，不会在卸载时重新写回。缓存操作失败时留在原编辑器并显示错误。
- 接受期间阻止应用内切换，防止重复提交；回调确认 project/proposal/scope/会话与原提交快照，即使程序重置编辑器也不能清除另一提案的草稿。
- P2：作者改回基线时清除旧自动缓存。恢复记录先取缓存，项目初始化不触发作者编辑的清理逻辑，避免新建表单缓存被误删。覆盖 Canon、Memory、Chapter、Scene、事实/知识与卷表单。
- 页面关闭继续使用浏览器原生离开保护；本机草稿不是正式正文，也不是跨设备存储。

新增/扩展证据：`proposal-acceptance.test.ts`、`proposal-draft.test.ts`、`autosave-scope.test.ts`、`narrative-maintenance.test.ts`、`manuscript-volumes.test.ts`。`structured-drafting.e2e.mjs` 在真实浏览器中验证离开三选项、刷新恢复及接受请求期间不能切换；界面截图位于 `.tmp/proposal-leave.png`。

## 性能结果

Windows 10 / i5-9400F / 32GiB，Vite 开发服务器、隔离 SQLite 与无 CPU 限速的 headless Chromium。每个重复动作采样 5 次；中位和最大值仅代表该次本机合成负载。优化前记录基于 `ee4bbfa` 加本轮草稿修复工作区，尚未实施性能改动。

| 操作 | 本轮优化前，999 场景 中位 / 最大 | 优化后，999 场景 中位 / 最大 | 验收 |
|---|---:|---:|---|
| 历史面板打开 | 5,658 / 26,026ms | **214 / 294ms** | 中位≤1秒、最大≤2秒，通过 |
| 场景切换 | 845 / 1,342ms | **80 / 107ms** | 中位≤200ms，通过 |
| 项目往返 | 3,687 / 6,293ms | **1,462 / 2,200ms** | 中位≤2秒，通过；最大值保留 |

| 优化后规模 | 历史面板中位 | 场景切换中位 | 项目往返中位 | 额外点击展开正文中位 |
|---|---:|---:|---:|---:|
| 20 场景 / 60 修订 | 80ms | 80ms | 592ms | 288ms |
| 200 场景 / 600 修订 | 96ms | 63ms | 706ms | 172ms |
| 999 场景 / 2,997 修订 | 214ms | 80ms | 1,462ms | 187ms |

前后三档均保持协议 2 的原始交互测量；新增正文展开测量和 DOM 上限断言。额外 trace 在计时循环结束后单独录制，避免 trace 开销进入预算样本。最后仅微调了分页复选框的行内布局，并由 small 档截图和构建复核。

实际改动：

1. 历史列表每页最多 50 个版本，比较菜单各最多 52 个选项（本页＋已选版本），正文明确展开后才挂载。可翻页、筛选当前场景、保留跨页比较选择和按 ID 恢复，真实总数不变。
2. 场景目录用按 scene ID 的派生集合查状态，按 chapter ID 预分组；避免每行扫描全部正文/提案。
3. 项目进入仍等待必要编辑数据与草稿恢复。graph/director/progress 在需要的面板加载，并保留 loading、错误/重试与项目隔离；不会通过提前关闭 loading 将未就绪编辑器计为完成。

性能证据支持这些改动：历史面板 layout 中位由约 **2,897ms 降到 7ms**；场景切换主线程 task 中位由约 **798ms 降到 27ms**。不是通过更换 SQLite 获得收益。

**本轮没有新增服务端分页。** 完整历史接口仍返回 **18,648,685 字节**，前端仍可获得全部历史正文，因此版本总数、审核来源读取、导出和备份保持原有语义。前端限制 DOM 已达到当前预算，按计划 T5 的条件分支暂不增加 API/DTO/迁移复杂度；更长版本链及更大附件仍需另测，不能把当前结果推广到任意容量。

固定数据：[优化前 large](../../performance/2026-09-08-before-large.json)、[small](../../performance/2026-09-08-small.json)、[medium](../../performance/2026-09-08-medium.json)、[large](../../performance/2026-09-08-large.json)、[large CDP trace](../../performance/2026-09-08-large-trace.json)。原始逐次样本及运行日志保留在 `.tmp/performance-*-progress.json` 和 `.tmp/performance-final-*.log`；各档截图已检查。

## 门禁与稳定性

- 后端：364 unittest 通过；Ruff check、233 文件 format check、compileall 通过。后端业务代码和数据库结构未改动。
- 前端：33 Node 检查＋125 Vitest 通过，lint 与生产 build 通过。新增历史行为测试验证 DOM 有界、正文按需显示、总数与跨页恢复目标正确。
- 当前完整 7 条 E2E 通过；包含真实 SQLite、审核、失败重试、刷新及重启路径。
- Step 8 接受记录尚未完成时原先仍可解析，存在使用旧规划的窗口。现已在接受与状态刷新期间阻止解析；测试通过延迟响应验证这一边界。该用例额外连续运行 **5 次，全部通过**。
- 三档 benchmark 均验证完整正文/历史恢复及超限写入被拒绝。large 使用 `--check-budgets` 实际断言全部四个时延门槛，退出 0；原始全历史 API 数量断言仍保留。

复测命令（仓库根目录）：

```powershell
rtk proxy node e2e/longform-benchmark.mjs --size large --trace --check-budgets
rtk proxy node e2e/longform-benchmark.mjs --size medium
rtk proxy node e2e/longform-benchmark.mjs --size small
```

无新增依赖、无真实作者数据或付费模型调用。远端 Actions、生产构建的交互性能、低配机器、长时间内存行为及真实模型效果仍未认证。
