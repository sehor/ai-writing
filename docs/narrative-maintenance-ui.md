# AUD-19：时态事实与知识作者界面契约

## 作者入口与单一事实系统

时态事实、读者知识和角色知识继续使用 AUD-18 的 `story_facts` / `knowledge_states` 权威数据，不新建第二套前端事实模型。作者在现有“故事设定”导航中展开“时态事实与知识”管理区；Graph 的 NarrativePanel 继续使用完整模式，因此结构分析页面仍能查看同一份叙事状态。

管理列表是作者视图，会显示 confirmed、planned、未来有效和暂未向读者公开的记录。它不是正文生成上下文。事实编辑支持主体、关系、值、闭区间有效场景、读者可见时点、来源和状态；已有事实更正要求填写原因并发送 `expected_version`。撤回保留记录与历史。知识编辑支持读者/角色知情时点、来源、状态、原因和版本化更正；`world_truth` 只读，由事实本身派生。

## 场景安全预览

“同场景知识对照”只调用：

`GET /projects/{project_id}/story-state?scene_position={sequence}&character={pov}`

前端不从作者管理列表自行推导世界真相、读者已知或角色已知，也不把未来/隐藏事实拼回预览。三栏分别显示 `world_truth`、`reader_knowledge`、`character_knowledge`，每条保留事实来源和版本。默认使用当前 SceneContract 的 sequence 与 POV，作者也可显式切换场景/角色。失败不会清空上一次成功的安全快照，可直接重试。

这一边界与正文/Reference 生成一致：真实生成仍由后端 `NarrativeSnapshot.for_scene()` 组装 scene-safe context。浏览器验收创建了当前事实与未来隐藏事实，证明场景 4 的预览和 Reference `used_context` 都只包含当前安全事实，不包含未来秘密。

## 草稿、切换和并发

事实和知识表单沿用统一 `draftSessions`：

- scope 分别为 `narrativeFact:{project}:{fact|new}` 与 `narrativeKnowledge:{project}:{fact}:{knowledge|new}`；
- 输入后由现有 400ms autosave 标 dirty 并写本地草稿；进入记录时按服务端内容建立 baseline，再恢复同 scope 缓存；
- 事实/知识选择切换使用统一 `confirmLeave`，项目切换和 beforeunload 由 workspace 汇总 `draftSnapshotEntries()`；
- 新项目 reset 会为“新建事实”表单建立 baseline，因此无需先点击按钮也能进入 dirty/autosave；已有记录草稿在再次选择该记录时恢复；
- 成功保存按服务端版本重新建 baseline；保存期间继续输入时保留为本地脏草稿；409 显示版本变化，不静默覆盖；
- 无效事实区间、读者可见时点或角色知情时点先在前端阻止，同时后端 422 仍是最终约束。

项目异步响应继续检查当前 `projectContext`；领域 store 不导入 workspace，因此不恢复旧的双向 store 依赖。

## 验收

新增 Pinia/组件测试覆盖事实详情、知识/历史、创建与更正 payload、world truth 只读、无效区间、草稿缓存恢复、失败重试和三栏安全预览；draft-safety 契约增加 Narrative 两个 scope。真实浏览器 E2E 使用临时 SQLite，经界面完成事实创建、角色知情、未来隐藏事实、场景预览和事实 v2 更正，再调用本地 Reference 生成验证上下文隔离。无外部或付费模型调用。
