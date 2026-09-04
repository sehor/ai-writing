"""Provider-neutral manuscript scene generation."""

from app.llm.gateway import GenerationPolicy, ModelGateway, ModelRequest
from app.llm.policy import generation_policy_for
from app.llm.runtime import ModelExecution, ModelRuntime, as_model_runtime
from app.models import ModelExecutionOptions
from app.prompts import compile_manuscript_prompt
from app.snowflake.contracts import ManuscriptSceneDraftContract
from app.snowflake.validators import structured_payload_from_content


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
    return as_model_runtime(runtime).execute(
        request,
        options,
        validate_content=_validate_manuscript_scene,
    )


def _validate_manuscript_scene(content: str) -> ManuscriptSceneDraftContract:
    payload = structured_payload_from_content(content)
    if payload:
        return ManuscriptSceneDraftContract.model_validate(payload)
    # Compatibility for gateways/tests that still return the former Markdown-only
    # response. New providers receive and should follow the version 2 JSON schema.
    prose = content.strip()
    if not prose:
        raise ValueError("Manuscript scene response is empty.")
    return ManuscriptSceneDraftContract(
        scene_id="legacy-provider-output",
        manuscript_prose=prose,
        scene_contract_coverage={
            "goal": "TBD",
            "conflict": "TBD",
            "turning_point": "TBD",
            "outcome": "TBD",
            "missing_elements": [],
        },
    )


__all__ = ["generate_manuscript_scene"]
