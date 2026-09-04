import re
import tempfile
import unittest
from pathlib import Path

from app.prompts.manager import PromptAssetError, PromptManager, PromptRenderError


class PromptManagerTests(unittest.TestCase):
    def test_loads_versions_and_renders_variables_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.toml"
            catalog.write_text(
                """schema_version = 1
[prompts.\"example\"]
version = \"1.2.3\"
template = \"Hello, ${name}!\"
""",
                encoding="utf-8",
            )
            manager = PromptManager(catalog)
            self.assertEqual(manager.version("example"), "1.2.3")
            self.assertEqual(manager.render("example", {"name": "author"}), "Hello, author!")
            with self.assertRaises(PromptRenderError):
                manager.render("example")

    def test_rejects_invalid_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.toml"
            catalog.write_text("schema_version = 9", encoding="utf-8")
            with self.assertRaises(PromptAssetError):
                PromptManager(catalog)

    def test_ten_step_method_assets_match_the_guidance_document_exactly(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        document = (project_root / "docs" / "snowflake-ten-step-prompt-spec.md").read_text(
            encoding="utf-8"
        )
        documented_prompts = re.findall(
            r"### \d+\.4 Step Prompt\s+~~~text\s*(.*?)\s*~~~",
            document,
            re.DOTALL,
        )
        self.assertEqual(len(documented_prompts), 10)

        manager = PromptManager()
        for step_number, documented in enumerate(documented_prompts, start=1):
            with self.subTest(step_number=step_number):
                asset = manager.get(f"snowflake.step{step_number:02d}.method")
                self.assertEqual(asset.template, documented.strip())


if __name__ == "__main__":
    unittest.main()
