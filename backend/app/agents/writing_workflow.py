from dataclasses import dataclass, field
from typing import Protocol

from app.models import (
    SnowflakeGenerationRequest,
    SnowflakeGenerationResponse,
    WorkflowAgentTrace,
)


class WorkflowNotConfiguredError(RuntimeError):
    def __init__(self, message: str, trace: list[WorkflowAgentTrace] | None = None):
        super().__init__(message)
        self.trace = trace or []


@dataclass
class WritingWorkflowState:
    request: SnowflakeGenerationRequest
    artifact: str = ""
    content: str = ""
    trace: list[WorkflowAgentTrace] = field(default_factory=list)

    def record(self, stage: str, agent_name: str, status: str) -> None:
        self.trace.append(
            WorkflowAgentTrace(stage=stage, agent_name=agent_name, status=status)
        )


class WorkflowAgent(Protocol):
    name: str
    stage: str

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        pass


class WritingWorkflow(Protocol):
    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        pass


class InterfaceOnlyWorkflowAgent:
    def __init__(self, name: str, stage: str):
        self.name = name
        self.stage = stage

    def run(self, state: WritingWorkflowState) -> WritingWorkflowState:
        state.record(self.stage, self.name, "declared")
        return state


class InterfaceOnlyWritingWorkflow:
    def __init__(self) -> None:
        self.pre_generation_agents: list[WorkflowAgent] = [
            InterfaceOnlyWorkflowAgent("project_context_loader", "pre_generation"),
            InterfaceOnlyWorkflowAgent("canon_constraint_checker", "pre_generation"),
            InterfaceOnlyWorkflowAgent("memory_retriever", "pre_generation"),
            InterfaceOnlyWorkflowAgent("prompt_planner", "pre_generation"),
        ]
        self.generation_agents: list[WorkflowAgent] = [
            InterfaceOnlyWorkflowAgent("draft_generator", "generation"),
        ]
        self.post_generation_agents: list[WorkflowAgent] = [
            InterfaceOnlyWorkflowAgent("consistency_reviewer", "post_generation"),
            InterfaceOnlyWorkflowAgent("style_reviewer", "post_generation"),
            InterfaceOnlyWorkflowAgent("artifact_normalizer", "post_generation"),
        ]

    def run_snowflake_generation(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        state = WritingWorkflowState(request=request)
        for agent in (
            self.pre_generation_agents
            + self.generation_agents
            + self.post_generation_agents
        ):
            state = agent.run(state)

        raise WorkflowNotConfiguredError(
            "Writing workflow implementation is not configured.",
            trace=state.trace,
        )
