"""Versioned prompt assets owned by the application."""

from app.prompts.models import PromptMessage, PromptPlan, ResponseContract
from app.prompts.registry import PromptDefinition, PromptRegistry, default_prompt_registry
from app.prompts.snowflake import compile_snowflake_prompt, register_snowflake_prompts
from app.prompts.creative import (
    compile_manuscript_prompt,
    compile_repair_prompt,
    compile_reference_prompt,
    compile_writeback_prompt,
    register_creative_prompts,
)


register_snowflake_prompts(default_prompt_registry)
register_creative_prompts(default_prompt_registry)


__all__ = [
    "PromptDefinition",
    "PromptMessage",
    "PromptPlan",
    "PromptRegistry",
    "ResponseContract",
    "compile_manuscript_prompt",
    "compile_repair_prompt",
    "compile_reference_prompt",
    "compile_snowflake_prompt",
    "compile_writeback_prompt",
    "default_prompt_registry",
]
