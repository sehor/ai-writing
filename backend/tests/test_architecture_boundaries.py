from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_agents_and_prompts_do_not_import_provider_configuration_or_sdk(self) -> None:
        forbidden = ("DeepSeekSettings", "get_openai_client", "from openai", "import openai")
        for directory in (APP_ROOT / "agents", APP_ROOT / "prompts"):
            for path in directory.glob("*.py"):
                content = path.read_text(encoding="utf-8")
                for token in forbidden:
                    self.assertNotIn(token, content, f"{path} crosses the model adapter boundary")

    def test_deepseek_adapter_does_not_import_domain_or_persistence_modules(self) -> None:
        adapter = (APP_ROOT / "llm" / "adapters" / "deepseek.py").read_text(encoding="utf-8")
        for module in ("app.data", "app.models", "app.services", "app.snowflake"):
            self.assertNotIn(module, adapter)


if __name__ == "__main__":
    unittest.main()
