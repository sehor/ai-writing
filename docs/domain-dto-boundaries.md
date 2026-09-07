# 领域 DTO 边界

后端定义在 `app/domain_models`，前端定义在 `src/types` 的领域模块。`app.models` 和 `types/index.ts` 仅显式再导出，保留已有调用者兼容性；领域模块直接导入所需的其他领域，不能导回兼容入口。后端保留原类名、字段、校验器及 JSON schema，前端保留原类型名与旧数据的可选元数据。

project、canon、scene、narrative、memory、model、graph 是基础定义；snowflake 依赖 model，reference 依赖 model/writeback，analysis 依赖 writeback，compiler 组合 scene/manuscript/writeback。Manuscript 的生成材料依赖既有 `snowflake/contracts.py` 纯结构契约，该文件不能依赖应用服务或 DTO 门面。禁止循环依赖，架构测试检查后端模块关系。

## 契约检查

`contracts/api-dtos.json` 记录正文生成审核、场景来源/版本、StoryFact、KnowledgeState 和历史记录的输出结构。后端测试直接比较 Pydantic 序列化 schema；前端 Node 测试用已有 TypeScript 编译器检查 DTO 字段和类型。新增关键字段时，后端 schema 变化会使测试失败；刷新后，前端类型遗漏或类型不符也会失败。不引入代码生成依赖。

在 backend 目录运行 `uv run --frozen --extra dev python scripts/export_api_contracts.py` 刷新，随后运行后端测试和 `pnpm test`/`pnpm build`。Windows 命令仍须遵循 RTK 约定。

真实行为由 narrative API/重开数据库回归、生成审核 API/备份回归、场景来源身份 API/备份回归，以及前端生成审核/场景回改组件测试覆盖。Schema 检查补充这些行为测试，不能替代它们。AUD-14 拆分时还对 110 个模型 schema 及完整 OpenAPI 作前后等值比较。
