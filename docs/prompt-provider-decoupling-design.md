# Prompt 管理与 LLM Provider 解耦设计

> 状态：Resilient Multi-Provider Implemented（OpenRouter、repair、自动切换、能力矩阵与 generation-run 已实施）
> 日期：2026-09-04
> 审查基线：`c4aa732`
> 适用范围：backend/app 下的 Snowflake、manuscript、reference、writeback 等生成流程
> 相关文档：docs/snowflake-business-loop-improvement-plan.md、docs/snowflake-ten-step-prompt-spec.md

## 0. 当前实施状态

`c4aa732` 已完成必要的业务前置条件：AI 结果进入待审核修订、Step 6–9 支持按记录生成与验证、Step 10 归入 Manuscript 审核链，并清除了 `open_threads` 作为生成依据的耦合。当前工作树又完成了本文的核心解耦范围。

已经完成：

- 建立静态 `PromptPlan`、`PromptRegistry` 和 `1.0.0` 版本 Prompt 资产；
- 建立供应商中立的 `ModelGateway`、统一结果/错误模型、DeepSeek adapter 和 Fake gateway；
- 完成 Snowflake、Manuscript、Reference、Writeback 的网关迁移；
- 保持 HTTP 路径、审核、接受、Canon 提交和本地 Snowflake fallback 语义；
- 增加 Prompt 快照、上下文边界、gateway 契约、Fake gateway 用例和架构守卫测试；
- 对 Step 6、9、10 配置独立输出预算，并把 `finish_reason=length` 作为截断失败处理。

扩展阶段现已完成 OpenRouter adapter、用户模型选择、最多一次受控 repair、兼容模型自动切换、静态能力矩阵及 generation-run/attempt 元数据持久化。持久层只保存安全元数据，不保存 API Key、完整 Prompt、作者正文或模型输出。远程 Prompt 平台仍延后；现有 Pydantic contracts、validators 与人工审核链继续复用。

### 0.1 多 Provider 运行规则（2026-09-04）

- 模型选择使用服务端允许列表中的 `model_profile`，客户端不能传任意 base URL、API Key 或 SDK 参数。
- 当前可选 OpenRouter 模型为 `google/gemini-3.8-flash` 与 `anthropic/claude-fable-5.1`；能力、上下文窗口和输出上限集中登记在 `app.llm.capabilities`。
- 结构化响应先执行本地 JSON、Pydantic 与领域校验；失败时同模型最多 repair 一次，仍失败后才按能力兼容的 profile 顺序切换。
- 鉴权失败不会自动切换，以免隐藏错误凭据；限流、超时、不可用、上下文溢出、截断、空响应和无效响应可以按策略切换。
- `generation_runs` 与 `generation_attempts` 记录 prompt/schema 版本、模型、错误码、耗时、token、repair/fallback 次数；记录随项目备份和恢复。

## 1. 决策摘要

项目应把“写什么、为什么这样写、输出必须满足什么条件”从 DeepSeek 等模型供应商实现中移出，形成独立的 Prompt 与领域契约层。

目标依赖方向如下：

~~~mermaid
flowchart TD
    A["雪花法领域规范"] --> B["Prompt 编译器"]
    B --> C["写作工作流"]
    C --> D["模型网关"]
    D --> E["Provider 适配器"]
    C --> F["输出校验器"]
    F --> G["应用服务提交"]
~~~

核心决策：

1. **雪花法规则属于领域层**：十步的目的、前置产物、必需字段、因果约束和验收规则，不属于任何 LLM Provider。
2. **Prompt 属于应用资产**：Prompt 由稳定的模板、版本、输入变量、响应契约和生成策略组成，通过注册表查找并由编译器生成 PromptPlan。
3. **Provider 只做协议适配**：DeepSeek、OpenAI、Anthropic、Gemini 等适配器只处理鉴权、HTTP/SDK、能力映射、超时、重试、用量和错误归一化，不包含 Snowflake、Canon 或 Scene Contract 的业务知识。
4. **工作流只做编排**：工作流负责收集上下文、选择 Prompt、调用网关、校验结果、产生 trace；不直接拼接大段 Prompt，也不依赖供应商配置类。
5. **外部响应先验证再进入业务**：LLM 输出是非可信外部输入，必须先经过结构解析和领域校验；“生成成功”不等于“业务产物有效”。
6. **迁移采用兼容式切片**：先无行为变化地抽出 Prompt，再引入通用网关，最后替换现有 DeepSeekWritingWorkflow，避免一次性重写整个生成链路。

最终效果是：更换模型时，仅新增或修改 Provider 适配器与注册配置；雪花法 Prompt、业务工作流、验证器和接口协议不需要随供应商一起重写。

## 2. 重构前耦合及其影响

以下表格记录审查基线中的问题，作为迁移依据；表中旧文件已在核心实施中替换或删除。

| 位置 | 当前职责 | 问题 |
|---|---|---|
| backend/app/agents/deepseek_workflow.py | 拼装 system/context/instruction Prompt、调用 DeepSeek、记录阶段 | 文件名和类名绑定供应商；Prompt 语义与传输代码混合；十步只有少量特判 |
| backend/app/integrations/provider_registry.py | 实现 WritingProvider 并实例化 DeepSeekWritingWorkflow | Provider 收到 datastore、steps、wiki 等业务对象，知道过多领域细节 |
| backend/app/agents/manuscript_workflow.py | 手写正文 Prompt，并直接依赖 DeepSeekSettings | 换供应商需要修改业务工作流 |
| backend/app/agents/reference_workflow.py | 手写参考资料 Prompt，并直接依赖 DeepSeekSettings | Prompt 无统一版本、契约和测试入口 |
| backend/app/agents/writeback_workflow.py | 手写回写 Prompt，并直接依赖 DeepSeekSettings | Canon 规则与 Provider 配置耦合 |
| backend/app/services/snowflake_service.py | 十步元数据、生成、保存、推进 | 步骤描述过于通用，不能作为精确的领域契约 |
| backend/app/agents/stage_protocol.py | 选择上游证据 | 只决定“带哪些资料”，不表达“本步必须遵守哪些雪花法规则” |

这种设计带来四个直接后果：

- 新增供应商时容易复制整个 DeepSeek 工作流，形成多份逐渐分叉的 Prompt。
- 修改雪花法规则时必须进入供应商文件，领域变更被误当成基础设施变更。
- 无法对 Prompt 做稳定的版本管理、快照测试和 A/B 对照。
- 供应商响应格式差异会向上泄漏，业务层难以建立一致的错误和校验语义。

## 3. 目标与非目标

### 3.1 目标

- 一个 Prompt 定义可被多个 Provider 和多个模型复用。
- 新增 Provider 时不修改 Snowflake、Canon、Scene Contract 的领域代码。
- Prompt 有稳定标识、版本、输入契约、输出契约和验证器。
- 工作流不 import DeepSeekSettings 或任何具体供应商 SDK。
- 所有供应商错误映射为统一错误类型。
- trace 能定位本次调用使用的 Prompt、模型、契约及验证结果。
- 支持模型能力差异，但不让供应商名称进入 Prompt 规则。
- 保留现有路由、服务和数据库契约，允许渐进迁移。

### 3.2 非目标

- 本设计不要求一次性支持所有供应商。
- 本设计不规定必须采用某个 Prompt 模板引擎；早期用纯 Python 构建器即可。
- 本设计不让 Prompt 注册表承担业务流程编排。
- 本设计不把本地确定性生成器伪装成远程 LLM；它可以实现同一生成运行时接口，但应保留清晰的 runtime kind。
- 本设计不在 Provider 适配器中修复不合格的小说内容。

## 4. 分层与所有权

### 4.1 雪花法领域层

负责表达稳定的业务知识：

- 每一步的目的和边界；
- 允许使用哪些上游产物；
- 原始雪花法规则与产品增强规则；
- 必填字段、因果约束和跨步不变量；
- 输出是否达到可接受状态；
- 哪些问题必须退回作者，哪些可以作为显式假设。

领域层不知道：

- DeepSeek、OpenAI 或其他供应商名称；
- HTTP、SDK、API Key、重试状态码；
- 某供应商的 response_format 参数名；
- Prompt 缓存等供应商专属字段。

建议的核心对象：

~~~python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SnowflakeStepSpec:
    step: int
    spec_id: str
    spec_version: str
    name: str
    purpose: str
    prerequisites: tuple[int, ...]
    semantic_rules: tuple[str, ...]
    response_schema: dict[str, Any]
    validator_id: str
    optional: bool = False
~~~

SnowflakeStepSpec 是领域定义，不应塞入长篇供应商提示词，也不应包含 temperature、model name 等参数。

### 4.2 Prompt 资产层

负责把领域规范、项目上下文和作者指令编译为可调用的 PromptPlan。

Prompt 不是一个裸字符串，而是一份有身份、有版本、有契约的资产：

~~~python
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class PromptMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ResponseContract:
    media_type: Literal["application/json", "text/markdown"]
    schema_name: str
    schema_version: str
    json_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class GenerationPolicy:
    temperature: float
    max_output_tokens: int
    timeout_seconds: float
    retry_class: str
    requires_structured_output: bool = True


@dataclass(frozen=True)
class PromptPlan:
    prompt_id: str
    prompt_version: str
    use_case: str
    messages: tuple[PromptMessage, ...]
    response_contract: ResponseContract
    generation_policy: GenerationPolicy
    metadata: dict[str, str] = field(default_factory=dict)
~~~

Prompt 编译器输入可以包含：

- project_snapshot：标题、类型、受众、篇幅等；
- author_direction：作者本轮明确要求；
- upstream_artifacts：当前步骤允许读取的上游产物；
- canon_constraints：已确认 Canon、禁止改写事实、开放问题；
- memory_context：风格与连续性提示；
- external_evidence：LLM Wiki 等引用资料；
- step_spec：当前步骤领域规范。

它输出 PromptPlan，而不是直接调用模型。

### 4.3 写作工作流层

工作流负责编排，不负责供应商协议：

1. 从 datastore 读取项目和上游产物。
2. 通过 StageProtocol 或等价组件筛选可用证据。
3. 从 StepSpecRegistry 获取当前步骤规范。
4. 调用 PromptCompiler 生成 PromptPlan。
5. 将 PromptPlan 交给 ModelGateway。
6. 解析并验证 ModelResult。
7. 生成待提交产物和 trace。
8. 由应用服务按现有策略保存、审核或推进。

工作流可以知道“这是 Snowflake Step 6”，但不应该知道“这是 DeepSeek chat completions”。

### 4.4 模型网关层

模型网关提供供应商无关的最小接口：

~~~python
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[PromptMessage, ...]
    response_contract: ResponseContract
    generation_policy: GenerationPolicy
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None


@dataclass(frozen=True)
class ModelResult:
    content: str
    provider_id: str
    model_id: str
    request_id: str | None
    finish_reason: str | None
    usage: TokenUsage
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class ModelGateway(Protocol):
    def complete(self, request: ModelRequest) -> ModelResult:
        ...
~~~

业务层只能依赖 ModelGateway 协议和统一数据对象，不能依赖 DeepSeek 客户端或响应类型。

### 4.5 Provider 适配器层

每个 Provider 适配器只负责：

- 读取并校验供应商配置；
- 把通用 messages 映射到供应商请求；
- 将结构化输出契约映射为 JSON Schema、tool call 或降级提示；
- 映射 temperature、max tokens、timeout 等通用生成策略；
- 执行 HTTP/SDK 调用；
- 处理安全的幂等重试；
- 解析文本、用量、request id、finish reason；
- 把供应商异常归一化；
- 报告能力，不改变领域语义。

Provider 适配器禁止：

- 判断 Step 2 有几次灾难；
- 为 Step 8 添加场景合同字段；
- 读取 datastore 或 SnowflakeArtifact；
- 自动确认 Canon；
- 拼接作者项目资料；
- 根据业务步骤偷偷改变 Prompt；
- 对小说内容做无法追踪的“修复”。

## 5. Provider 能力而不是 Provider 分支

不同模型确实有差异，但差异应通过能力协商表达，而不是在业务代码中写 if provider == "deepseek"。

~~~python
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    supports_system_messages: bool
    supports_json_schema: bool
    supports_tool_calls: bool
    supports_prompt_cache: bool
    max_context_tokens: int
    max_output_tokens: int
~~~

建议的降级顺序：

1. 原生 JSON Schema；
2. 供应商 tool/function schema；
3. JSON mode；
4. 严格文本指令 + 本地 JSON 解析与一次 repair；
5. 若契约仍不满足，返回 validation error，而不是把坏数据当成功。

如果模型的 max_output_tokens 无法承载 Step 6、Step 9 或 Step 10，工作流必须切分任务或选择更合适的模型；不能静默截断。

## 6. 已实施目录结构

核心实施采用以下最小结构；没有为尚未需要的能力、错误或 use case 拆出空模块：

~~~text
backend/app/
  snowflake/
    step_specs.py
    contracts.py
    validators.py
    renderers.py
  prompts/
    models.py
    registry.py
    snowflake.py
    creative.py
  llm/
    gateway.py
    registry.py
    policy.py
    fake.py
    adapters/
      deepseek.py
  agents/
    snowflake_workflow.py
    manuscript_workflow.py
    reference_workflow.py
    writeback_workflow.py
~~~

职责约束：

- snowflake：业务定义和验证；
- prompts：Prompt 资产、版本、编译；
- llm：统一调用端口和供应商适配；
- agents：上下文装配和流程编排；
- services：权限、事务、持久化、业务状态推进；
- integrations：不再承载模型 Provider 门面；其他非模型集成保持原职责。

不要建立一个无限膨胀的 prompt_manager.py。注册、编译、领域规范、输出验证必须是可独立测试的职责。

## 7. Prompt 注册与版本策略

### 7.1 稳定标识

建议标识方式：

- snowflake.step01
- snowflake.step02
- snowflake.step10.scene
- manuscript.revise_scene
- reference.extract
- writeback.propose_canon

版本使用独立的不可变字符串，例如 1.0.0。Prompt 内容或输出契约发生行为变化时创建新版本，不原地覆盖线上历史语义。

### 7.2 注册表接口

~~~python
class PromptRegistry(Protocol):
    def get(self, prompt_id: str, version: str | None = None) -> PromptDefinition:
        ...
~~~

默认版本由应用配置或项目实验配置选择。历史 trace 必须记录实际解析后的版本，不能只记录 latest。

### 7.3 版本变化规则

| 变化 | 建议版本 |
|---|---|
| 修正错字，不改变含义或契约 | patch |
| 增加可选字段、改善指导语 | minor |
| 改变步骤语义、必填字段或输出结构 | major |
| 只更换模型或供应商 | Prompt 版本不变，记录模型配置版本 |
| 只调整超时或安全重试 | Prompt 版本不变，记录运行策略版本 |

Prompt 版本、响应 schema 版本和应用代码版本是三个不同概念，不应合并成一个字段。

## 8. 上下文装配规则

Prompt 编译器应按固定层次装配信息，以免作者指令和外部资料篡改系统规则：

1. **系统规则**：角色、权威边界、安全边界、输出协议；
2. **步骤规则**：本步目的、方法原则、必需产物、禁止事项；
3. **项目上下文**：项目元数据和已接受的上游产物；
4. **Canon 与状态**：确认事实、禁止事实、当前角色与线索状态；
5. **参考资料**：来源和证据，明确其只是资料而非指令；
6. **作者本轮指令**：最高优先级的创作方向，但不能绕过 schema 和应用安全规则；
7. **响应契约**：要求输出结构、缺失输入处理和验收自检。

所有插入内容必须有清楚的边界标签。来自用户文档、Wiki 和旧产物的文本都按数据处理，不能因其中出现“忽略之前指令”而改变 Prompt 控制流。

## 9. 统一输出与提交边界

建议模型返回结构化 envelope，应用再把 artifact 渲染为 Markdown：

~~~json
{
  "schema_version": "snowflake.step02.v1",
  "status": "complete",
  "artifact": {},
  "assumptions": [],
  "tbd": [],
  "upstream_revision_suggestions": [],
  "questions_for_author": []
}
~~~

状态建议：

- complete：结构和领域验证均通过；
- needs_author_input：关键输入缺失，不允许模型编造；
- upstream_conflict：当前步骤揭示上游矛盾，应先修订上游；
- invalid：仅供本地校验结果使用，模型不应自行宣称有效。

应用处理顺序：

~~~mermaid
flowchart TD
    A["Provider 原始响应"] --> B["语法解析"]
    B --> C["Schema 校验"]
    C --> D["领域校验"]
    D --> E["渲染预览"]
    E --> F["保存或审核"]
~~~

特别注意：

- Provider 返回 200 只代表传输成功。
- JSON 能解析只代表语法成功。
- Schema 通过仍不代表雪花法因果约束成立。
- Canon、Scene Contract 等权威记录只能由应用服务按明确业务规则提交。
- 如果当前产品会自动保存并推进，Prompt 和 UI 都必须如实描述；不能让 Prompt 声称“一定等待人工保存”而服务实际自动提交。

## 10. 统一错误模型

建议错误层级：

| 错误 | 含义 | 默认处理 |
|---|---|---|
| ModelConfigurationError | API Key、endpoint、model 配置无效 | 不重试，返回可操作配置错误 |
| ModelAuthenticationError | 鉴权失败 | 不重试 |
| ModelRateLimitError | 限流 | 按 Retry-After 或退避重试 |
| ModelTimeoutError | 超时 | 有预算时安全重试 |
| ModelUnavailableError | 供应商临时不可用 | 安全重试或切换已配置模型 |
| ModelContextOverflowError | 输入超过上下文 | 重新选择/压缩上下文，不盲目重试 |
| ModelOutputTruncatedError | 输出达到上限而未完成 | 分段生成或提高上限 |
| ModelResponseParseError | 响应无法解析为目标格式 | 最多一次受控 repair |
| ModelResponseValidationError | 结构可解析但违反 schema/领域规则 | 返回明确字段错误，必要时定向修复 |
| ModelSafetyRefusalError | 模型拒绝 | 向上层保留拒绝原因，不伪造成空成功 |

Provider 原始错误码可以放在内部 cause 或安全 metadata 中，但 API 不应把供应商内部响应原样暴露给客户端。

## 11. Trace、隐私与可观测性

每次生成至少记录：

- run_id；
- use_case；
- prompt_id 与 prompt_version；
- response schema 名称与版本；
- provider_id 与 model_id；
- generation policy 版本；
- 上游 artifact id/revision 摘要；
- 输入/输出 token；
- 延迟、重试次数、finish reason；
- parse/schema/domain validation 结果；
- 是否发生 repair、降级或人工介入。

默认不要把完整作者正文、Canon、API Key 或原始 Prompt 写入普通日志。需要诊断时可存：

- Prompt 模板哈希；
- 变量名和长度；
- 经过脱敏的摘要；
- 受访问控制且有保留期限的调试快照。

trace 阶段名应保持供应商中立，例如：

- context_selected
- prompt_compiled
- model_requested
- model_responded
- response_parsed
- response_validated
- artifact_proposed
- artifact_committed

不再使用会把业务流程绑定到某一家供应商的阶段名。

## 12. 缓存边界

缓存键不能只由 prompt 文本组成，至少应包含：

- prompt_id/version；
- response schema version；
- model_id 与重要模型参数；
- 项目和上游产物 revision；
- Canon snapshot revision；
- 作者指令摘要；
- 外部证据 revision；
- 应用认可的 cache policy version。

创作生成通常不应默认跨项目共享缓存。涉及作者私有内容时，缓存必须与项目或租户隔离。

## 13. 渐进迁移计划

### Phase 0：建立行为基线（已完成）

- 为现有 DeepSeek Prompt 生成增加 characterization tests。
- 固定几个最小项目样例，记录 messages、调用参数和 trace。
- 不追求输出文本逐字相同，只固定输入装配和协议行为。

退出条件：可以判断后续重构是否意外改变当前接口和保存逻辑。

### Phase 1：抽出 Prompt 编译器，不改运行行为（已完成）

- 从 deepseek_workflow.py 抽出共享 system/context/instruction 生成。
- 建立 PromptPlan、PromptRegistry 和首批 snowflake Prompt 定义。
- DeepSeekWritingWorkflow 暂时仍调用原有客户端，但只消费 PromptPlan。
- 对每个 Prompt 做快照测试和变量缺失测试。

退出条件：deepseek_workflow.py 不再包含雪花法长 Prompt 字符串。

### Phase 2：引入 ModelGateway 与 DeepSeekAdapter（已完成）

- 建立统一请求、响应、能力和错误类型。
- 把鉴权、HTTP/SDK、用量、finish reason 处理移入 DeepSeekAdapter。
- 保持现有 provider 配置兼容，通过适配层读取旧配置。
- 工作流依赖 ModelGateway，不依赖 DeepSeekSettings。

退出条件：工作流可以用 FakeModelGateway 完成全链路测试。

### Phase 3：建立通用 SnowflakeWorkflow（已完成）

- 将 DeepSeekWritingWorkflow 改名/替换为供应商中立的 SnowflakeWorkflow。
- 把 step 规则移入 SnowflakeStepSpec 与 validators。
- 保持 WritingWorkflow 对上层的兼容接口，先不强制路由和服务改签名。
- trace 改用供应商中立阶段名。

退出条件：SnowflakeWorkflow 源码中不存在具体供应商 import 或名称分支。

### Phase 4：迁移其他生成流程（已完成）

依次迁移：

1. manuscript_workflow.py；
2. reference_workflow.py；
3. writeback_workflow.py。

每个流程都使用独立 prompt_id、response schema 和领域 validator；共享的只是 Prompt 基础设施与 ModelGateway。

退出条件：agents 目录不再 import DeepSeekSettings。

### Phase 5：用第二个适配器证明边界（OpenRouter 与增强 Fake/Recording 已完成）

已实现 OpenRouter adapter，并继续用可编排延迟与异常的 Fake gateway 做无真实 Key 的确定性测试。

证明点：

- 相同 PromptPlan 可发往两个实现；
- 新 Provider 不修改 prompts、snowflake、agents 目录；
- 能力不足时走可预测降级或明确失败；
- Provider 响应差异被统一模型隔离。

### Phase 6：清理兼容层（核心清理已完成）

- 标记高层 WritingProvider 旧接口为 deprecated。
- 删除不再使用的 DeepSeekPromptPlanner 空壳。
- 在调用点完全迁移后再删除 DeepSeekWritingWorkflow。
- 更新架构文档和开发者指南。

不要在同一个提交里同时移动所有文件、改变输出 schema、改变保存策略并接入第二供应商；否则回归原因无法定位。

## 14. 测试策略

### 14.1 Prompt 单元测试

- registry 能按 id/version 精确解析；
- 所有必需变量缺失时明确失败；
- Prompt 消息顺序和边界标签稳定；
- Prompt 快照不包含供应商名称；
- 外部资料中的指令文本不会进入系统控制层；
- Step 1 至 Step 10 各有独立 prompt_id 和契约。

### 14.2 领域契约测试

- Step 2 必须含 setup、三次灾难和 ending；
- Step 2 的第二、第三次灾难能追溯到主角行动；
- Step 3 能区分 motivation 和 goal；
- Step 7 必须表达人物变化，不能被 Canon 清单替代；
- Step 8 每场景都有稳定 id、POV 和事件；
- Step 9 被标记为 optional；
- Step 10 按场景生成，并能报告与设计文档的偏离。

### 14.3 Provider 契约测试

对每个 adapter 运行同一套测试：

- messages 映射；
- 结构化输出能力映射；
- 超时、限流、鉴权、服务不可用；
- finish reason 和 token usage；
- 截断检测；
- 错误归一化；
- 不记录 secret 和完整私有正文。

### 14.4 工作流集成测试

使用 FakeModelGateway：

- 给定固定上游产物，断言生成的 PromptPlan；
- 返回合法 fixture，断言产物进入预览/保存流程；
- 返回非法 JSON、缺字段和领域冲突，断言不会提交；
- 验证 trace 中包含 prompt/schema/model 版本；
- 验证自动保存或人工审核策略与 UI、Prompt 一致。

### 14.5 架构守卫

可用静态检查或测试保持边界：

- backend/app/prompts 不 import backend/app/llm/adapters；
- backend/app/llm/adapters 不 import snowflake 领域对象；
- backend/app/agents 不 import DeepSeekSettings 或供应商 SDK；
- 新增 Provider 只需要 adapter、配置与 registry wiring；
- 供应商名称不出现在 Snowflake Prompt 资产中。

## 15. API 与兼容性

外部 HTTP API 不必因本次重构立即改变。现有 router -> service -> workflow 边界可以保留。

若未来需要客户端选择模型，应暴露稳定的 model profile 或 runtime profile，而不是把任意供应商参数透传给前端。例如允许选择：

- balanced-writing；
- long-context-planning；
- low-cost-draft。

由后端把 profile 解析为 provider/model/policy。这样前端不会与某家供应商的 model id、temperature 约束或专属字段耦合。

如果确实需要管理员级 Provider 配置，应使用独立管理接口，并验证白名单字段；不得允许普通生成请求覆盖 endpoint、API Key 或任意 SDK 参数。

## 16. 备选方案及取舍

### 方案 A：只把 Prompt 字符串移到 prompts.py

不采用。它能减小单个文件，但没有版本、输入/输出契约、验证和 Provider 边界；换模型时仍会复制工作流。

### 方案 B：每个 Provider 各维护一套 Prompt

不采用。模型差异会被放大成领域语义分叉，同一步骤在不同供应商下可能产生不同业务合同，测试和迁移成本持续上升。

允许存在少量**能力适配文本**，例如没有原生 JSON Schema 时加入结构化输出提醒，但它必须由通用降级策略生成，不能复制整套业务 Prompt。

### 方案 C：引入重量级第三方 Prompt 平台后再重构

暂不采用。当前首要问题是代码边界错误，而不是缺少远程平台。先建立内部 PromptPlan 和 Registry，未来可以在不改变工作流接口的情况下接入外部存储、实验或评估平台。

### 方案 D：让 Provider 直接接收 datastore 和业务实体

不采用。这样 Provider 会继续承担上下文选择和业务规则，无法成为可替换的基础设施适配器。

## 17. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 抽象过度，简单调用变复杂 | 保持 ModelGateway 接口最小；先迁移一个用例再扩展 |
| 结构化输出降低文学生成质量 | 规划步骤结构化；正文可在 envelope 的 prose 字段中保留自由文本 |
| 不同模型遵循 JSON 的能力不同 | 能力协商、一次 repair、严格本地校验和清晰失败 |
| Prompt 版本增多难维护 | 明确 owner、变更日志、弃用周期和默认版本 |
| 迁移时新旧链路行为不一致 | characterization tests、feature flag、逐用例切换 |
| 长步骤被 token 上限截断 | 预估预算、分段策略、finish reason 检查 |
| 自动 repair 改坏内容 | repair 只修语法/缺字段，不擅自重写已接受的故事事实 |
| 日志泄露作者内容 | 默认记录哈希和元数据，正文调试快照受控且短期保留 |

## 18. 完成标准

满足以下条件才视为解耦完成：

- [x] 十步雪花法都有独立、版本化的 Prompt 定义和响应契约。
- [x] SnowflakeWorkflow、ManuscriptWorkflow、ReferenceWorkflow、WritebackWorkflow 不依赖具体供应商配置或 SDK。
- [x] DeepSeekAdapter 不读取 datastore，不理解 Snowflake step，不提交 Canon。
- [x] 同一个 PromptPlan 能通过 FakeModelGateway 和 DeepSeekAdapter。
- [x] 新增第二 Provider 不修改领域层、Prompt 资产和工作流。
- [ ] 所有 LLM 响应经过 parse、schema、domain 三层验证后才能提交。
- [ ] trace 包含 prompt、schema、provider、model 和验证版本。
- [x] Step 6/9/10 有明确的长输出 token 预算，并对截断结果失败关闭。
- [x] Prompt、UI 与服务的“自动保存/人工确认”语义一致：AI 输出进入待审核修订，接受后才更新权威状态。
- [x] 高层 WritingProvider 和供应商命名工作流已在调用点迁移后删除；现有 HTTP 接口保持兼容。

## 19. 与现有雪花改进计划的关系

docs/snowflake-business-loop-improvement-plan.md 关注业务闭环、产物状态、Canon 和 Scene Contract 等产品能力；本文关注生成基础设施的责任边界。

两者的关系是：

- 业务改进计划定义“系统应该产出和确认什么”；
- 本文定义“这些生成任务如何在不绑定供应商的前提下执行”；
- docs/snowflake-ten-step-prompt-spec.md 定义“每一步具体怎样提示和验收”。
- docs/prompt-management.md 定义“版本化 Prompt 资产怎样脱离 Python 源码加载、渲染和变更”。

三份文档应共同实施。只做 Prompt 文案而不建立 Provider 边界，会继续累积耦合；只做 Provider 抽象而不修正十步语义，则只是更方便地调用多个模型去生成同样不准确的产物。
