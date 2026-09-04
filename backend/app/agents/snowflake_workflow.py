"""Provider-neutral Snowflake generation workflow."""

from app.agents.writing_workflow import (
    CanonConstraintChecker,
    LlmWikiContextCollector,
    LocalArtifactNormalizer,
    LocalConsistencyReviewer,
    MemoryRetriever,
    ProjectContextLoader,
    WorkflowAgent,
    WritingWorkflowState,
)
from app.data import WritingDataStore
from app.llm.gateway import (
    GenerationPolicy,
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
)
from app.llm.policy import generation_policy_for
from app.llm.runtime import ModelRuntime, as_model_runtime
from app.llm_wiki.interfaces import LlmWiki
from app.models import SnowflakeGenerationRequest, SnowflakeGenerationResponse, SnowflakeStep
from app.prompts import compile_snowflake_prompt
from app.snowflake.validators import (
    validate_snowflake_payload,
    validate_snowflake_record_generation,
)


class SnowflakePromptCompiler:
    name = "prompt_compiler"
    stage = "pre_generation"

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.prompt_plan = compile_snowflake_prompt(state)
        state.record(
            self.stage,
            self.name,
            "compiled",
            prompt_id=state.prompt_plan.prompt_id,
            prompt_version=state.prompt_plan.prompt_version,
            schema_name=state.prompt_plan.response_contract.schema_name,
            schema_version=state.prompt_plan.response_contract.schema_version,
        )
        return state


class GatewayDraftGenerator:
    name = "model_gateway"
    stage = "generation"

    def __init__(self, runtime: ModelRuntime, policy: GenerationPolicy | None = None) -> None:
        self.runtime = runtime
        self.policy = policy

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        if state.prompt_plan is None:
            raise RuntimeError("Snowflake prompt must be compiled before model generation.")
        request = ModelRequest(
            prompt=state.prompt_plan,
            policy=self.policy or generation_policy_for(state.prompt_plan),
            metadata={
                "project_id": state.request.project_id,
                "step_number": str(state.request.step_number),
            },
        )
        try:
            execution = self.runtime.execute(
                request,
                state.request,
                validate_content=lambda content: _validate_generated_content(state, content),
            )
        except ModelGatewayError as exc:
            exc.trace = list(state.trace)
            raise
        result = execution.completion.result
        state.content = result.content
        state.record(
            self.stage,
            self.name,
            f"called {result.model_id}",
            prompt_id=state.prompt_plan.prompt_id,
            prompt_version=state.prompt_plan.prompt_version,
            schema_name=state.prompt_plan.response_contract.schema_name,
            schema_version=state.prompt_plan.response_contract.schema_version,
            provider_id=result.provider_id,
            model_id=result.model_id,
            finish_reason=result.finish_reason or "",
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            generation_run_id=execution.generation_run_id,
            attempt_count=execution.attempt_count,
            repair_count=execution.repair_count,
            fallback_count=execution.fallback_count,
        )
        return state


class SnowflakeWorkflow:
    def __init__(
        self,
        data_store: WritingDataStore,
        steps: list[SnowflakeStep],
        runtime: ModelRuntime | ModelGateway,
        llm_wiki: LlmWiki,
        policy: GenerationPolicy | None = None,
    ) -> None:
        self.agents: list[WorkflowAgent] = [
            ProjectContextLoader(data_store, steps),
            CanonConstraintChecker(data_store),
            MemoryRetriever(data_store),
            LlmWikiContextCollector(llm_wiki),
            SnowflakePromptCompiler(),
            GatewayDraftGenerator(as_model_runtime(runtime), policy),
            LocalConsistencyReviewer(),
            LocalArtifactNormalizer(),
        ]

    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        state = WritingWorkflowState(request=request)
        for agent in self.agents:
            state = agent.run(state)
        return SnowflakeGenerationResponse(
            project_id=request.project_id,
            step_number=request.step_number,
            artifact=state.artifact,
            content=state.content,
            workflow_trace=state.trace,
            validation_report=state.validation_report,
        )


def _validate_generated_content(state: WritingWorkflowState, content: str) -> object:
    if state.request.step_number in {6, 7, 8, 9}:
        records, report = validate_snowflake_record_generation(
            state.request.step_number,
            content,
            state.request.target_record_ids or None,
        )
        if report.status == "failed":
            raise ValueError("Snowflake record response failed its contract.")
        return records
    report = validate_snowflake_payload(state.request.step_number, content)
    if report.status == "failed":
        raise ValueError("Snowflake response failed its contract.")
    return report


__all__ = ["SnowflakeWorkflow"]
