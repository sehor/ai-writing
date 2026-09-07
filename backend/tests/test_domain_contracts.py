import ast
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import models
from app.data import SQLiteWritingDataStore, get_data_store
from app.domain_models.narrative import KnowledgeState, StoryFact
from app.domain_models.project import ProjectCreate
from app.http_errors import install_application_error_handlers
from app.routers.narrative import router
from scripts.export_api_contracts import FIXTURE, contract_schemas


DOMAIN_ROOT = Path(__file__).resolve().parents[1] / "app" / "domain_models"


class DomainContractTests(unittest.TestCase):
    def test_shared_output_schemas_are_current(self):
        self.assertEqual(
            json.loads(FIXTURE.read_text(encoding="utf-8")),
            contract_schemas(),
            "Refresh with uv run python scripts/export_api_contracts.py and check frontend consumers.",
        )

    def test_compatibility_exports_are_the_original_domain_classes(self):
        for path in DOMAIN_ROOT.glob("*.py"):
            module = importlib.import_module(f"app.domain_models.{path.stem}")
            for name, value in vars(module).items():
                if (
                    isinstance(value, type)
                    and issubclass(value, BaseModel)
                    and value is not BaseModel
                ):
                    self.assertIs(getattr(models, name), value)
                    value.model_json_schema()  # No unresolved cross-module forward references.

    def test_domain_imports_are_acyclic_and_never_use_facade_or_infrastructure(self):
        graph = {}
        for path in DOMAIN_ROOT.glob("*.py"):
            modules = [
                node.module or ""
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                if isinstance(node, ast.ImportFrom)
            ]
            for module in modules:
                self.assertFalse(
                    module.startswith(
                        ("app.models", "app.data", "app.services", "app.routers", "fastapi")
                    ),
                    f"{path.name}: {module}",
                )
            graph[path.stem] = [
                m.rsplit(".", 1)[1] for m in modules if m.startswith("app.domain_models.")
            ]

        def visit(name, ancestors):
            self.assertNotIn(name, ancestors, f"Domain cycle: {ancestors} -> {name}")
            for target in graph[name]:
                visit(target, [*ancestors, name])

        for name in graph:
            visit(name, [])

    def test_author_metadata_survives_api_and_reopened_database(self):
        with TemporaryDirectory() as temp:
            database = Path(temp) / "author.db"
            store = SQLiteWritingDataStore(database)
            store.init()
            project = store.create_project(
                ProjectCreate(title="Contract", premise="An author corrects a secret.")
            )
            app = FastAPI()
            install_application_error_handlers(app)
            app.include_router(router, prefix="/api")
            app.dependency_overrides[get_data_store] = lambda: store
            with TestClient(app) as client:
                base = f"/api/projects/{project.id}/story-facts"
                response = client.post(
                    base,
                    json={
                        "subject": "Mira",
                        "predicate": "owns",
                        "value": "Key",
                        "valid_from_scene": 3,
                        "reader_visible_from": 4,
                        "source_ref": "author:chapter-2",
                    },
                )
                self.assertEqual(response.status_code, 201, response.text)
                fact = StoryFact.model_validate(response.json())
                payload = fact.model_dump(exclude={"id", "project_id", "version", "updated_at"})
                payload.update(
                    value="Letter", expected_version=fact.version, reason="Correct source"
                )
                corrected = client.put(f"{base}/{fact.id}", json=payload)
                self.assertEqual(corrected.status_code, 200, corrected.text)
                stored = SQLiteWritingDataStore(database).get_story_fact(project.id, fact.id)
                self.assertEqual(corrected.json(), stored.model_dump(mode="json"))
                self.assertEqual(stored.version, 2)
                self.assertEqual(stored.source_ref, "author:chapter-2")
                self.assertTrue(stored.updated_at)
                knowledge = client.get(f"{base}/{fact.id}/knowledge-states")
                self.assertEqual(knowledge.status_code, 200)
                states = [KnowledgeState.model_validate(item) for item in knowledge.json()]
                self.assertEqual(
                    states,
                    SQLiteWritingDataStore(database).list_knowledge_states(project.id, fact.id),
                )
                self.assertEqual(
                    {state.scope for state in states}, {"world_truth", "reader_knowledge"}
                )
