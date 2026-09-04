"""Provider-neutral manuscript scene generation."""

from app.llm.gateway import GenerationPolicy, ModelGateway, ModelRequest
from app.llm.policy import generation_policy_for
from app.llm.runtime import ModelExecution, ModelRuntime, as_model_runtime
from app.models import ModelExecutionOptions
from app.prompts import compile_manuscript_prompt


def generate_manuscript_scene(
    runtime: ModelRuntime | ModelGateway,
    context: str,
    project_id: str = "",
    options: ModelExecutionOptions | None = None,
    policy: GenerationPolicy | None = None,
) -> ModelExecution:
    prompt = compile_manuscript_prompt(context)
    request = ModelRequest(
        prompt=prompt,
        policy=policy or generation_policy_for(prompt),
        metadata={"project_id": project_id},
    )
    return as_model_runtime(runtime).execute(request, options)


__all__ = ["generate_manuscript_scene"]
