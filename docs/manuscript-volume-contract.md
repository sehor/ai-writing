# 卷组织兼容契约（AUD-21，2026-09-07）

卷是可选的展示/导出组织，不是叙事时间轴，也不是正文所有者。迁移19新增 manuscript_volumes 与 manuscript_volume_chapters；不修改旧 chapter/scene/revision ID 或旧 DTO。旧项目与 schema≤18 备份保持未分卷，不猜测归属。

卷序号1–999，卷名去首尾空白后1–160字。卷按 sequence、id 排序；卷内章节按原章节 sequence、id；场景按原 scene.sequence。允许相同卷排序号，以稳定ID打破并列。章节仍使用项目内序号，不因为移动卷而重排；叙事事实有效期、读者和角色知情位置完全不变。

## 接口与数据边界

GET/POST `/api/projects/{project_id}/manuscript/volumes` 读取/创建卷。PUT/DELETE `/api/projects/{project_id}/manuscript/volumes/{volume_id}` 更名、改排序/删除。

PUT `/api/projects/{project_id}/manuscript/chapters/{chapter_id}/volume` 接收 `{volume_id}`；空字符串表示未分卷。每章最多归属一个卷；两组复合外键阻止跨项目卷或章节关联。变更经数据端口与 VolumeRepository，在 write=True UoW 中提交。

删卷只级联删除关联表，不删除章节、场景或正文。删除章节会清理归卷关联。新增卷包含 chapter_ids；旧章节接口无需传新字段。没有卷时 Markdown 导出完全保留旧格式；有卷时输出卷→章→场景，未分卷章节/未分章场景独立列出，正文只出现一次。空卷显示无正式正文说明。

## 草稿与界面

正文设置的 VolumeManager 提供新建、更名、排序、删卷和章节归属。删除前明确确认会保留内容；归属操作立即保存，不触发正文版本。目录支持空卷、未分卷及卷名/章名/场景名搜索。

卷表单由 manuscript 门面内唯一 volumes 模块持有，使用 `volume:{project}:{id|new}` 缓存、冻结保存快照与已有关页/切项目保护；取消切换保留原草稿，旧项目请求不能覆盖新项目。保存失败保留表单并可重试。刷新卷列表与写操作互斥，避免迟到读取覆盖刚保存的组织。未装配卷编辑器的独立正文 store 不产生虚假卷草稿。

备份明确登记新表及读取校验，导入先在临时数据库验证外键和记录。兼容历史测试夹具不再给旧schema带入不存在的新卷表。

## 验证与限制

新增5项后端迁移、备份、导出、CRUD与跨项目验证，6项前端草稿/状态/目录/组件测试；真实浏览器 `e2e/manuscript-volumes.e2e.mjs` 覆盖创建、更名、排序、归卷移动、刷新恢复、项目隔离、删卷与内容保留。截图 `.tmp/manuscript-volumes.png` 已检查。

完整门禁：360 backend unittest、31 Node +112 Vitest、Ruff check/format、compileall、lint/build和6条E2E通过；日志 `.tmp/aud21-backend.log`。

本功能不提供多作者协同编辑/卷元数据冲突合并；两个窗口同时修改卷元数据仍按最后一次成功写入，不影响正文乐观锁。真实作者项目和付费模型效果未参与本轮验收。
