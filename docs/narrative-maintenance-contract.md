# AUD-18：事实和知识更正契约

## 目标与边界

作者可修正/撤回故事事实及读者、角色知识，查看每次变化的内容、来源、原因和版本。保留现有事实 ID 与关联，不物理删除。非 confirmed 记录不进入写作 snapshot；不将规划内容自动升级为事实。现有架构 FastAPI → 数据端口 → 单个 SQLite UoW 保持。

事实使用闭区间 `[valid_from_scene, valid_to_scene]`，空结束位置表示持续有效。读者/角色获知位置必须落在事实有效期内；查询位置继续按事实有效期与知识获知时刻共同过滤。world_truth 知识由事实派生，不能通过作者知识接口单独编辑。

## API 与状态

- `PUT /projects/{project_id}/story-facts/{fact_id}`：完整更正字段 + `expected_version`、非空 `reason`。保留 ID，递增 version，写入不可变历史。source_ref 可更正，旧来源留在历史。
- `POST /projects/{project_id}/story-facts/{fact_id}/retract`：expected_version + reason，状态置为 retracted，关联知识一并撤回并保留历史。
- `GET /projects/{project_id}/story-facts/{fact_id}/history`：返回该事实及其知识的历史快照，含目标 ID、version、reason、created_at、record。
- `GET /projects/{project_id}/story-facts/{fact_id}/knowledge-states`：返回所有确认/待确认/撤回知识及版本，便于作者复核。
- `POST /projects/{project_id}/story-facts/{fact_id}/knowledge-states`：新建读者或角色知识；重复身份返回409，world_truth 返回422。
- `PUT /projects/{project_id}/story-facts/{fact_id}/knowledge-states/{knowledge_id}`：完整知识字段 + expected_version + reason；scope/character 身份不可改变。
- `POST /projects/{project_id}/story-facts/{fact_id}/knowledge-states/{knowledge_id}/retract`：撤回并保留记录。

更正事实会重建 world_truth 与显式 reader_visible_from 对应的读者知识；既有角色知识降为 planned，需作者逐项确认。撤回事实会撤回全部关联知识。再次确认事实必须走完整更正，不能自动恢复角色知情。确认知识要求其事实已确认。

knowledge_states 是知识权威；兼容 reader_visible_from 与旧角色知识表随写入同步。旧 character-knowledge 写入保留兼容并记历史，修改会推进版本，使新接口的过期版本检查有效。错误语义：跨项目/不存在的目标404，过期版本或重复身份409，时间/状态/身份不合法422。修改、校验、派生同步和历史记录置于一个 BEGIN IMMEDIATE 事务。

## 持久化与兼容

迁移16为 story_facts/knowledge_states 增加 version（默认1）及 updated_at，新增 narrative_revisions 记录完整内容快照。历史引用通过复合外键限制在同一项目/事实内。创建写入初始历史；旧记录首次改变前补存原始基线。旧数据库和 schema≤15 备份允许没有新字段/历史表；新备份完整包含历史并验证快照和引用一致。撤回保留所有实体，避免悬空引用。

代码范围：models、narrative router/repository、邻接维护模块、数据端口/store、迁移与 backup 格式校验。前端维护界面留给 AUD-19，不扩展关系/故事线模型。

## 实现与验证顺序

1. 模型/迁移及纯历史读取写入；采用现有 Pydantic + sqlite3 风格，无新依赖。
2. 事务更正/撤回、知识同步、项目/时间/状态验证；路由复用应用异常映射。
3. API 与直接数据测试覆盖旧版本、跨项目 ID、边界位置、回滚、知识失效、撤回后 snapshot 不泄漏。
4. 迁移15→16、旧备份导入、新备份历史 round-trip 与恶意关联拒绝；再跑全套。

在 backend 目录执行：

```powershell
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev python -m unittest discover -s tests -q
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev ruff check app tests
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev ruff format --check app tests
rtk proxy uv --cache-dir ../.tmp/uv-cache run --frozen --extra dev python -m compileall -q app
```

所有验证使用临时 SQLite、合成小说数据，不操作作者真实数据库。
