"""Application-owned generation policies, independent of model providers."""

from types import MappingProxyType

from app.llm.gateway import GenerationPolicy
from app.prompts.models import PromptPlan


DEFAULT_MAX_OUTPUT_TOKENS = 2400
MAX_OUTPUT_TOKENS_BY_PROMPT = MappingProxyType(
    {
        "snowflake.step06": 4800,
        "snowflake.step09": 4000,
        "snowflake.step10.scene": 4800,
        "reference.suggestion": 1600,
        "writeback.propose": 2400,
    }
)


def generation_policy_for(prompt: PromptPlan) -> GenerationPolicy:
    """Return a stable output budget for one prompt use case."""
    return GenerationPolicy(
        max_output_tokens=MAX_OUTPUT_TOKENS_BY_PROMPT.get(
            prompt.prompt_id,
            DEFAULT_MAX_OUTPUT_TOKENS,
        )
    )


__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "MAX_OUTPUT_TOKENS_BY_PROMPT",
    "generation_policy_for",
]
