from app.agents.deepseek_workflow import DeepSeekSettings
from app.agents.writing_workflow import WorkflowNotConfiguredError


def build_provider_scene_draft(settings: DeepSeekSettings, context: str) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise WorkflowNotConfiguredError(
            "The OpenAI-compatible SDK is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc

    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    response = client.chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You draft prose for AI Writing Studio. Use the provided scene contract, "
                    "Canon constraints, and cognition module context. Return only manuscript prose "
                    "in Markdown. Do not create or confirm new Canon facts. If required information "
                    "is missing, keep it ambiguous instead of inventing facts."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(
                    [
                        "Draft this writing scope as reviewable manuscript prose.",
                        "",
                        "Context package:",
                        context,
                    ]
                ),
            },
        ],
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
    content = response.choices[0].message.content if response.choices else ""
    if not content:
        raise ValueError("empty provider response")
    return content.strip()
