from typing import Protocol

from app.models import SnowflakeGenerationRequest, SnowflakeGenerationResponse


class AgentNotConfiguredError(RuntimeError):
    pass


class WritingAgent(Protocol):
    def generate_snowflake_artifact(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        pass


class UnconfiguredWritingAgent:
    def generate_snowflake_artifact(
        self, request: SnowflakeGenerationRequest
    ) -> SnowflakeGenerationResponse:
        raise AgentNotConfiguredError("Writing agent implementation is not configured.")
