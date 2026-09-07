"""Generate review material through the real service using a controlled, free gateway."""

import json
from pathlib import Path
import sys

from app.data import SQLiteWritingDataStore
from app.llm import FakeModelGateway, ModelGatewayRegistry
from app.services.manuscript_service import ManuscriptService

data_root, project_id, scene_id = sys.argv[1:]
store = SQLiteWritingDataStore(Path(data_root) / "app.db")
material = {
    "scene_id": scene_id,
    "manuscript_prose": "修复师在灯塔下发现了一封信。",
    "entry_state_observed": ["尚未找到信件"],
    "exit_state_produced": ["保留信件"],
    "scene_contract_coverage": {
        "goal": "发现信件", "conflict": "地址已消失", "turning_point": "发现背面线索",
        "outcome": "保留信件", "missing_elements": ["下一步行动的代价"],
    },
    "new_fact_candidates": [{
        "claim": "信封上有旧邮戳", "entity_refs": ["信件"],
        "reason_introduced": "提供调查线索", "status": "proposal",
    }],
    "design_deviation_proposals": [{
        "target_artifact_ref": "step:8", "current_design": "立刻寄出信件",
        "proposed_change": "暂时保留信件", "reason": "继续调查",
        "downstream_impact": ["调整下一场景的开场"],
    }],
    "continuity_questions": ["旧邮戳来自哪里？"],
    "source_refs": [f"scene:{scene_id}"],
}
gateway = FakeModelGateway([json.dumps(material, ensure_ascii=False)])
registry = ModelGatewayRegistry()
registry.register("deepseek", lambda: gateway)
service = ManuscriptService(data_store=store, cognition=None)
service.gateway_registry = registry
print(service.generate_provider_proposal(project_id, scene_id).model_dump_json())
