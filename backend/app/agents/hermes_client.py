from app.models import (
    HermesProcessingIssue,
    HermesRevisionProcessResult,
    ManuscriptRevision,
    SceneContract,
)
from app.text_utils import one_line, safe_slug
from typing import Any, Protocol


class HermesAgentTransport(Protocol):
    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        pass


class HermesAgentClient:
    """Client boundary for the external Hermes agent server."""

    def __init__(self, transport: HermesAgentTransport | None = None):
        self.transport = transport or VirtualHermesAgentServer()

    def process_manuscript_revision(
        self,
        project_id: str,
        project_title: str,
        revision: ManuscriptRevision,
        scene_contract: SceneContract,
    ) -> HermesRevisionProcessResult:
        payload = build_process_revision_payload(
            project_id,
            project_title,
            revision,
            scene_contract,
        )
        response = self.transport.post_json("/agent/tasks/process-manuscript-revision", payload)
        return HermesRevisionProcessResult.model_validate(response)


class VirtualHermesAgentServer:
    """Local mock for the external Hermes agent server API."""

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path != "/agent/tasks/process-manuscript-revision":
            return {
                "status": "failed",
                "summary": f"Unknown virtual Hermes endpoint: {path}",
                "wiki_changes": [],
                "issues": [
                    {
                        "severity": "error",
                        "code": "unknown_endpoint",
                        "message": f"Unknown virtual Hermes endpoint: {path}",
                        "source_ref": payload.get("source_ref", ""),
                    }
                ],
                "writeback_proposals": [],
                "processed_source_ref": payload.get("source_ref", ""),
            }
        return virtual_process_revision(payload)


def build_process_revision_payload(
    project_id: str,
    project_title: str,
    revision: ManuscriptRevision,
    scene_contract: SceneContract,
) -> dict[str, Any]:
    source_ref = f"manuscript_revision:{revision.id}"
    return {
        "task": "ai_writing.llm_wiki.process_manuscript_revision",
        "project": {
            "id": project_id,
            "title": project_title,
        },
        "revision": {
            "id": revision.id,
            "scene_id": revision.scene_id,
            "proposal_id": revision.proposal_id,
            "title": revision.title,
            "version": revision.version,
            "content": revision.content,
            "created_at": revision.created_at,
        },
        "scene_contract": {
            "id": scene_contract.id,
            "sequence": scene_contract.sequence,
            "title": scene_contract.title,
            "pov": scene_contract.pov,
            "goal": scene_contract.goal,
            "conflict": scene_contract.conflict,
            "turning_point": scene_contract.turning_point,
            "required_canon": scene_contract.required_canon,
            "forbidden_facts": scene_contract.forbidden_facts,
            "open_threads": scene_contract.open_threads,
            "source_artifact_step": scene_contract.source_artifact_step,
        },
        "source_ref": source_ref,
        "idempotency_key": f"{project_id}:{revision.id}",
    }


def virtual_process_revision(payload: dict[str, Any]) -> dict[str, Any]:
    project = payload["project"]
    revision = payload["revision"]
    scene_contract = payload["scene_contract"]
    source_ref = payload["source_ref"]
    issues = contract_issues(revision, scene_contract, source_ref)
    wiki_changes = [
        {
            "path": f"raw/confirmed/{revision['id']}.md",
            "action": "created",
            "reason": "Virtual Hermes stored the confirmed manuscript revision as source material.",
        },
        {
            "path": f"scenes/{scene_contract['sequence']:03d}-{safe_slug(scene_contract['title'])}.md",
            "action": "updated",
            "reason": "Virtual Hermes refreshed the scene continuity page from the new revision.",
        },
        {
            "path": "log.md",
            "action": "updated",
            "reason": "Virtual Hermes logged the manuscript revision processing run.",
        },
    ]
    proposals = [
        {
            "target": "memory_record",
            "action": "create",
            "title": f"Hermes chapter note: {revision['title']}",
            "rationale": (
                "Virtual Hermes processed the newly saved chapter through the external agent "
                "interface and returned a Memory candidate for review."
            ),
            "source_ref": source_ref,
            "payload": {
                "record_type": "chapter_summary",
                "title": f"{revision['title']} continuity note",
                "scope": revision["scene_id"],
                "content": build_chapter_note(project["title"], revision, scene_contract),
                "tags": "hermes, manuscript revision, chapter continuity",
                "source_ref": source_ref,
            },
        }
    ]
    return {
        "status": "partial" if issues else "completed",
        "summary": (
            f"Virtual Hermes processed {revision['title']} v{revision['version']} for {project['title']}. "
            "The app sent only the revision delta and Scene Contract; the external wiki update is simulated."
        ),
        "wiki_changes": wiki_changes,
        "issues": [issue.model_dump() for issue in issues],
        "writeback_proposals": proposals,
        "processed_source_ref": source_ref,
    }


def contract_issues(
    revision: dict[str, Any],
    scene_contract: dict[str, Any],
    source_ref: str,
) -> list[HermesProcessingIssue]:
    issues: list[HermesProcessingIssue] = []
    content = revision["content"].lower()
    forbidden_hits = [
        item
        for item in split_contract_terms(scene_contract["forbidden_facts"])
        if item.lower() in content
    ]
    if forbidden_hits:
        issues.append(
            HermesProcessingIssue(
                severity="warning",
                code="scene_contract_forbidden_fact",
                message=(
                    "Virtual Hermes found text that appears to touch forbidden facts: "
                    + ", ".join(forbidden_hits[:5])
                ),
                source_ref=source_ref,
            )
        )
    if scene_contract["pov"] and scene_contract["pov"].lower() not in content:
        issues.append(
            HermesProcessingIssue(
                severity="info",
                code="pov_not_explicit",
                message=(
                    f"The Scene Contract POV is {scene_contract['pov']}, but the revision does not "
                    "explicitly mention that name. Review if the POV is still clear in prose."
                ),
                source_ref=source_ref,
            )
        )
    return issues


def build_chapter_note(
    project_title: str,
    revision: dict[str, Any],
    scene_contract: dict[str, Any],
) -> str:
    excerpt = one_line(revision["content"], 800)
    return "\n".join(
        [
            f"Project: {project_title}",
            f"Scene: {scene_contract['sequence']}. {scene_contract['title']}",
            f"Revision: {revision['id']} v{revision['version']}",
            f"Goal: {scene_contract['goal'] or 'No scene goal recorded.'}",
            f"Conflict: {scene_contract['conflict'] or 'No scene conflict recorded.'}",
            f"Turning point: {scene_contract['turning_point'] or 'No turning point recorded.'}",
            "",
            "Revision excerpt:",
            excerpt,
        ]
    )


def split_contract_terms(value: str) -> list[str]:
    terms = []
    for raw in value.replace(";", "\n").replace(",", "\n").splitlines():
        term = raw.strip(" -\t")
        if len(term) >= 4:
            terms.append(term)
    return terms
