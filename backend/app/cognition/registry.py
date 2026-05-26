from pathlib import Path

from app.cognition.interfaces import (
    CommittedContentEvent,
    ContextPacket,
    ModuleReport,
    ProjectCognitionSnapshot,
    WritingScope,
)
from app.cognition.infra_graph import LocalInfraGraphModule
from app.cognition.llm_wiki import LocalLlmWikiModule
from app.cognition.memplace import LocalMemplaceModule


class CognitionRegistry:
    def __init__(self, modules_root: Path):
        self.graph_module = LocalInfraGraphModule(modules_root)
        self.wiki_module = LocalLlmWikiModule(modules_root)
        self.memplace_module = LocalMemplaceModule(modules_root)
        self.modules = [
            self.wiki_module,
            self.memplace_module,
        ]

    def prepare_context(
        self,
        snapshot: ProjectCognitionSnapshot,
        scope: WritingScope,
    ) -> list[ContextPacket]:
        return [
            module.prepare_context(snapshot, scope)
            for module in self.modules
        ]

    def ingest_committed_content(
        self,
        snapshot: ProjectCognitionSnapshot,
        event: CommittedContentEvent,
    ) -> list[ModuleReport]:
        return [
            module.ingest_committed_content(snapshot, event)
            for module in self.modules
        ]


modules_root = Path(__file__).resolve().parent.parent.parent / "data" / "projects"
cognition_registry = CognitionRegistry(modules_root)


def get_cognition_registry() -> CognitionRegistry:
    return cognition_registry
