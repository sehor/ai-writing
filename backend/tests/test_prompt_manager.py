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

    def test_ten_step_method_assets_are_complete_and_versioned(self) -> None:
        manager = PromptManager()
        expected_ids = {
            f"snowflake.step{step_number:02d}.method" for step_number in range(1, 11)
        }
        configured_ids = {
            asset.asset_id for asset in manager.assets() if asset.asset_id.endswith(".method")
        }
        self.assertEqual(configured_ids, expected_ids)

        for step_number in range(1, 11):
            with self.subTest(step_number=step_number):
                asset = manager.get(f"snowflake.step{step_number:02d}.method")
                self.assertEqual(asset.version, "2.0.0")
                self.assertEqual(manager.render(asset.asset_id), asset.template)


if __name__ == "__main__":
    unittest.main()
