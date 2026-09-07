"""Refresh the small set of output schemas checked by both backend and frontend tests."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain_models.manuscript import ManuscriptGenerationReview
from app.domain_models.narrative import KnowledgeState, NarrativeRevision, StoryFact
from app.domain_models.scene import SceneContract
from app.domain_models.reference import ReferenceEditorContext

CONTRACTS = (
    ManuscriptGenerationReview,
    SceneContract,
    StoryFact,
    KnowledgeState,
    NarrativeRevision,
    ReferenceEditorContext,
)
FIXTURE = Path(__file__).resolve().parents[2] / "contracts" / "api-dtos.json"


def contract_schemas() -> dict:
    return {model.__name__: model.model_json_schema(mode="serialization") for model in CONTRACTS}


if __name__ == "__main__":
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(
        json.dumps(contract_schemas(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Updated {len(CONTRACTS)} API contracts: {FIXTURE}")
