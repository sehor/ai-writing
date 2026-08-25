from app.config import resolve_data_root
from app.llm_wiki.interfaces import LlmWiki
from app.llm_wiki.local_backend import LocalFileLlmWiki


projects_root = resolve_data_root() / "projects"
llm_wiki: LlmWiki = LocalFileLlmWiki(projects_root)


def get_llm_wiki() -> LlmWiki:
    return llm_wiki
