import inspect
import unittest

from app.narrative import NarrativeSnapshot
from app.services.compile_service import CompileService, build_compile_context
from app.services.manuscript_service import ManuscriptService
from app.services.reference_service import ReferenceService
from app.dependencies import get_reference_service


class NarrativeSnapshotBoundaryTests(unittest.TestCase):
    def test_scene_snapshot_has_no_legacy_llm_wiki_contract(self) -> None:
        self.assertNotIn("llm_wiki", inspect.signature(NarrativeSnapshot.for_scene).parameters)
        self.assertNotIn("wiki_context", NarrativeSnapshot.__dataclass_fields__)

    def test_scene_context_consumers_have_no_legacy_llm_wiki_dependency(self) -> None:
        for consumer in (
            CompileService.__init__,
            ManuscriptService.__init__,
            ReferenceService.__init__,
            get_reference_service,
            build_compile_context,
        ):
            with self.subTest(consumer=consumer.__qualname__):
                parameters = inspect.signature(consumer).parameters
                self.assertNotIn("llm_wiki", parameters)
                self.assertNotIn("llm_wiki_context", parameters)


if __name__ == "__main__":
    unittest.main()
