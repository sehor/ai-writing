from typing import Any
from app.agents.writing_workflow import WorkflowNotConfiguredError

def get_openai_client(api_key: str, base_url: str | None = None) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise WorkflowNotConfiguredError(
            "The OpenAI-compatible SDK is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc
    return OpenAI(api_key=api_key, base_url=base_url)
