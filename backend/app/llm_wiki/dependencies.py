from pathlib import Path

from app.llm_wiki.interfaces import LlmWiki
from app.llm_wiki.local_backend import LocalFileLlmWiki


projects_root = Path(__file__).resolve().parents[2] / "data" / "projects"
llm_wiki: LlmWiki = LocalFileLlmWiki(projects_root)


def get_llm_wiki() -> LlmWiki:
    return llm_wiki
