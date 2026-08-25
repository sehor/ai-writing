"""Environment-driven paths for the local-first backend.

Everything defaults to the historical layout ('<backend>/data') so an
installation without the environment variables behaves exactly as before;
AI_WRITING_DATA_ROOT exists so browser E2E runs can point the whole app
(SQLite database + LLM wiki project files) at a throwaway directory.
"""

import os
from pathlib import Path

# backend/app/config.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parents[1]

DATA_ROOT_ENV_VAR = "AI_WRITING_DATA_ROOT"


def resolve_data_root() -> Path:
    """Directory holding the SQLite database and per-project wiki files."""
    configured = os.environ.get(DATA_ROOT_ENV_VAR, "")
    if configured:
        return Path(configured).expanduser().resolve()
    return BACKEND_ROOT / "data"
