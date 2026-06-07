import json
from hashlib import sha256
from pathlib import Path

from app.llm_wiki.interfaces import (
    WikiConstraint,
    WikiContextQuery,
    WikiContextResult,
    WikiEvidence,
    WikiIngestionResult,
    WikiInsight,
    WikiInsightQuery,
    WikiInsightResult,
    WikiSourceDocument,
)
from app.llm_wiki.stage_protocol import get_stage_policy


class LocalFileLlmWiki:
    def __init__(self, projects_root: Path):
        self.projects_root = projects_root

    def ingest(self, document: WikiSourceDocument) -> WikiIngestionResult:
        project_path = self._project_path(document.project_id)
        source_path = self._source_path(project_path, document)
        status = "updated" if source_path.is_file() else "stored"
        if document.supersedes:
            self._mark_superseded(project_path, document.supersedes)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(
            json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return WikiIngestionResult(
            status=status,
            source_ref=document.source_ref,
            stored_path=source_path.relative_to(project_path).as_posix(),
            superseded_source_ref=document.supersedes,
        )

    def retrieve_context(self, query: WikiContextQuery) -> WikiContextResult:
        policy = get_stage_policy(query.snowflake_step)
        documents = [
            document
            for document in self._load_documents(query.project_id)
            if self._is_visible(document, query, policy.planned_source_steps, policy.include_observed)
        ]
        documents.sort(
            key=lambda item: (
                item.story_position if item.story_position is not None else -1,
                item.snowflake_step,
                item.source_ref,
            )
        )
        evidence = [
            WikiEvidence(
                source_ref=document.source_ref,
                title=document.title,
                excerpt=excerpt(document.content),
                knowledge_class=document.knowledge_class,
                snowflake_step=document.snowflake_step,
                scope=document.scope,
                story_position=document.story_position,
            )
            for document in documents
        ]
        constraints = [
            WikiConstraint(
                text=evidence_item.excerpt,
                source_refs=[evidence_item.source_ref],
            )
            for evidence_item in evidence
        ]
        return WikiContextResult(
            summary=(
                f"Retrieved {len(evidence)} stage-aware LLM Wiki source"
                f"{'' if len(evidence) == 1 else 's'} for Snowflake step {query.snowflake_step}."
            ),
            evidence=evidence,
            constraints=constraints,
        )

    def analyze(self, query: WikiInsightQuery) -> WikiInsightResult:
        context = self.retrieve_context(WikiContextQuery(**query.model_dump()))
        planned_refs = [
            item.source_ref
            for item in context.evidence
            if item.knowledge_class == "planned"
        ]
        observed_refs = [
            item.source_ref
            for item in context.evidence
            if item.knowledge_class == "observed"
        ]
        if query.snowflake_step == 10 and planned_refs and not observed_refs:
            insights = [
                WikiInsight(
                    kind="observed_context_gap",
                    summary="No earlier observed prose is available for this drafting position.",
                    detail=(
                        "Use the planned evidence as provisional guidance and avoid treating "
                        "unwritten state changes as facts."
                    ),
                    source_refs=planned_refs,
                )
            ]
        elif observed_refs:
            insights = [
                WikiInsight(
                    kind="continuity_evidence",
                    summary="Earlier observed prose is available for continuity review.",
                    detail=(
                        "Check the current draft against these source revisions before confirming "
                        "new state changes."
                    ),
                    source_refs=observed_refs,
                )
            ]
        elif planned_refs:
            insights = [
                WikiInsight(
                    kind="planned_source_coverage",
                    summary="Upstream planning evidence is available for this stage.",
                    detail="Use these sources to check causal coverage and stage alignment.",
                    source_refs=planned_refs,
                )
            ]
        else:
            insights = []
        return WikiInsightResult(
            summary=f"Generated {len(insights)} advisory LLM Wiki insight(s).",
            insights=insights,
        )

    def _project_path(self, project_id: str) -> Path:
        return self.projects_root / project_id / "modules" / "llm_wiki"

    def _source_path(
        self,
        project_path: Path,
        document: WikiSourceDocument,
    ) -> Path:
        digest = sha256(document.source_ref.encode("utf-8")).hexdigest()[:20]
        return project_path / "sources" / document.knowledge_class / f"{digest}.json"

    def _load_documents(self, project_id: str) -> list[WikiSourceDocument]:
        sources_path = self._project_path(project_id) / "sources"
        if not sources_path.is_dir():
            return []
        documents: list[WikiSourceDocument] = []
        for path in sources_path.rglob("*.json"):
            documents.append(
                WikiSourceDocument.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            )
        return documents

    def _mark_superseded(self, project_path: Path, source_ref: str) -> None:
        sources_path = project_path / "sources"
        if not sources_path.is_dir():
            return
        for path in sources_path.rglob("*.json"):
            document = WikiSourceDocument.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if document.source_ref != source_ref:
                continue
            path.write_text(
                json.dumps(
                    document.model_copy(update={"status": "superseded"}).model_dump(
                        mode="json"
                    ),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return

    @staticmethod
    def _is_visible(
        document: WikiSourceDocument,
        query: WikiContextQuery,
        planned_source_steps: tuple[int, ...],
        include_observed: bool,
    ) -> bool:
        if document.status != "approved":
            return False
        if query.scope and document.scope and query.scope != document.scope:
            return False
        if document.knowledge_class == "planned":
            if document.snowflake_step not in planned_source_steps:
                return False
            if (
                query.spoiler_horizon is not None
                and document.story_position is not None
                and document.story_position > query.spoiler_horizon
            ):
                return False
            return True
        if not include_observed:
            return False
        if (
            query.story_position is not None
            and document.story_position is not None
            and document.story_position > query.story_position
        ):
            return False
        return True


def excerpt(value: str, limit: int = 800) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."
