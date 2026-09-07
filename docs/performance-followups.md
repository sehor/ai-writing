# 实测性能后续项（由 AUD-22 建立）

状态：仅本地后续任务，未发布GitHub、未在本轮实施。测量与固定数据见 [性能基线](./performance-baseline.md)。这些任务不属于原23项中未完成的漏项；AUD-22要求先测量，再为实测问题建立具体优化项。

## PERF-01 · 优先限制历史面板的完整正文DOM渲染

证据：999场景/2,997修订下，历史HTTP完整响应18,648,685字节，中位433ms；打开面板中位4,985ms、最大20,003ms，CDP layout中位2,940ms。200场景/600修订已需868ms。全量历史/正文一次加载和渲染是明确需要调查的路径，但20秒长尾的完整因果尚未profile证实。

范围：`frontend/src/components/manuscript/RevisionHistory.vue`、`frontend/src/stores/manuscript/history.ts`、`backend/app/data/repositories/manuscript.py`。先录trace区分列表项/正文预览/比较控件的DOM成本；优先按需展开正文和当前场景历史，不先引入通用分页框架。必要的分页须保留按ID读取、版本比较、恢复及完整导出/备份，不得以丢历史换速度。

验收：同一合成夹具、同机协议2重测；999档面板中位≤1秒、5次最大≤2秒，首屏响应和DOM规模有界；所有版本仍可定位/比较/恢复，完整备份哈希不变。新增回归，记录前后耗时/负载/资源；慢机器另测而不是改变标准掩盖退化。

## PERF-02 · 定位场景切换主线程和项目辅助数据全量加载

证据：999档场景切换中位845ms，CDP task804ms、layout约1ms；项目切换往返中位3.67秒，graph/director/progress部分请求达到1.4–1.6秒。目录每场景执行 `.some` 扫描正文和提案数组，以及辅助数据全量加载，是代码可见的候选原因；需trace/调用计数确认，不能把候选当作已证实单一瓶颈。

范围：`frontend/src/components/ManuscriptWorkspace.vue`、`frontend/src/domain/manuscriptOrganization.ts`、`frontend/src/stores/workspace.ts` 和实际profile命中的后端辅助读取。可评估按scene_id建立派生索引、减少无关重算或延迟非当前面板加载；不得恢复workspace与领域循环依赖，不变更当前编辑会话/dirty/缓存权威。

验收：999档场景切换中位≤200ms，项目往返≤2秒；对应trace证明减少的工作；跨项目晚响应、离开取消、未保存草稿、规划过期指示和目录状态全部回归通过。作为独立实现提交，不与历史面板修改无边界并行。

## 后续观察而非当前阻断

大档约5.69MiB ZIP需要110MiB Python分配峰值，备份导出中位2.8秒。现有256MiB展开预算不等于进程只占256MiB。先增加附件/更多历史测量再决定是否采用流式备份；尚未证实内存泄漏，不应据单次峰值作该结论。
