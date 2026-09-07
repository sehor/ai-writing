# Copilot 选区求助契约（AUD-16）

正式正文的本地编辑草稿和待审核正文草稿共用选区入口。请求包含 project_id、scene_id、source_kind、proposal_id、expected_scene_version、session_id、原文 snapshot_text、selection_start/end、selected_text 和 selection_mode。偏移采用浏览器 UTF-16 码元，后端校验边界及原文匹配，支持中文和 emoji。没有选区时明确使用整场景；空白草稿不能发起请求。

前端冻结点击时的请求。当前项目、场景、提案、版本、内容或组件会话变化后将旧请求标为过期，必须重新选择；切换期间返回的请求不能自动激活为新编辑器的建议。选区不从草稿缓存自动恢复，刷新后重新捕获。写作问题等原有参考表单仍可独立使用。

后端核对请求所属项目、实际场景、正式正文版本，以及提案的场景和 pending_review 状态；允许未保存的 snapshot_text 与已保存正文不同。生成前和落库前均检查目标版本。选区文本是作者草稿，不是权威事实；使用当前场景安全 NarrativeSnapshot，加选区与有界周边文本作为模型上下文。本地和 provider 共用上下文与来源。

ReferenceSuggestion 增加可空 editor_context 字段，原样保存作者来源；迁移 17 使用可空 JSON 列，旧记录与旧备份默认为 null。来源字段由应用赋值，不能由模型改写。完整快照保存在结构字段，prompt/used_context 只保留有界内容。整个流程不写正文、Canon 或知识状态。

AUD-17 在此基础上增加独立的应用/预览/撤销操作，并再次验证目标和原文；接受参考建议状态不等于应用建议。
