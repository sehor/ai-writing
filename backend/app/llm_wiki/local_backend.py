import json
import re
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
from app.text_utils import one_line, slugify


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
        self._write_markdown_source(source_path.with_suffix(".md"), document)
        self._rebuild_projection(project_path, document.project_id)
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
                -self._score_document(item, query),
                item.story_position if item.story_position is not None else -1,
                item.snowflake_step,
                item.source_ref,
            )
        )
        evidence = [
            WikiEvidence(
                source_ref=document.source_ref,
                title=document.title,
                excerpt=self._projection_summary(document),
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
        if not context.evidence:
            insights = [
                WikiInsight(
                    kind="stage_context_gap",
                    summary="No stage-visible LLM Wiki evidence is available.",
                    detail=(
                        "Continue with user-provided context only, or save upstream "
                        "Snowflake artifacts before asking the wiki for constraints."
                    ),
                    source_refs=[],
                )
            ]
        elif query.snowflake_step == 10 and planned_refs and not observed_refs:
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

    def _write_markdown_source(self, path: Path, document: WikiSourceDocument) -> None:
        lines = [
            "---",
            f"project_id: {json.dumps(document.project_id, ensure_ascii=False)}",
            f"source_kind: {json.dumps(document.source_kind, ensure_ascii=False)}",
            f"source_ref: {json.dumps(document.source_ref, ensure_ascii=False)}",
            f"title: {json.dumps(document.title, ensure_ascii=False)}",
            f"snowflake_step: {document.snowflake_step}",
            f"artifact_type: {json.dumps(document.artifact_type, ensure_ascii=False)}",
            f"knowledge_class: {json.dumps(document.knowledge_class, ensure_ascii=False)}",
            f"status: {json.dumps(document.status, ensure_ascii=False)}",
            f"version: {document.version}",
            f"supersedes: {json.dumps(document.supersedes, ensure_ascii=False)}",
            f"scope: {json.dumps(document.scope, ensure_ascii=False)}",
            f"story_position: {json.dumps(document.story_position)}",
            "---",
            "",
            document.content.strip(),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")

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
            updated = document.model_copy(update={"status": "superseded"})
            path.write_text(
                json.dumps(
                    updated.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self._write_markdown_source(path.with_suffix(".md"), updated)
            return

    def _rebuild_projection(self, project_path: Path, project_id: str) -> None:
        documents = [
            document
            for document in self._load_documents(project_id)
            if document.status == "approved"
        ]
        documents.sort(
            key=lambda item: (
                item.snowflake_step,
                item.story_position if item.story_position is not None else -1,
                item.title,
                item.source_ref,
            )
        )
        concepts_path = project_path / "wiki" / "concepts"
        concepts_path.mkdir(parents=True, exist_ok=True)
        for path in concepts_path.glob("*.md"):
            if path.is_file():
                path.unlink()
        pages = []
        for document in documents:
            slug = self._concept_slug(document)
            (concepts_path / f"{slug}.md").write_text(
                self._concept_page(slug, document),
                encoding="utf-8",
            )
            pages.append((slug, document))
        self._write_projection_index(project_path / "wiki" / "index.md", pages)

    def _concept_slug(self, document: WikiSourceDocument) -> str:
        digest = sha256(document.source_ref.encode("utf-8")).hexdigest()[:10]
        return f"{slugify(document.title, 'source')}-{digest}"

    def _concept_page(self, slug: str, document: WikiSourceDocument) -> str:
        summary = self._projection_summary(document)
        lines = [
            "---",
            f"title: {json.dumps(document.title, ensure_ascii=False)}",
            'kind: "concept"',
            f"summary: {json.dumps(summary, ensure_ascii=False)}",
            f"sources: {json.dumps([document.source_ref], ensure_ascii=False)}",
            f"source_ref: {json.dumps(document.source_ref, ensure_ascii=False)}",
            f"source_kind: {json.dumps(document.source_kind, ensure_ascii=False)}",
            f"knowledge_class: {json.dumps(document.knowledge_class, ensure_ascii=False)}",
            f"snowflake_step: {document.snowflake_step}",
            f"artifact_type: {json.dumps(document.artifact_type, ensure_ascii=False)}",
            f"scope: {json.dumps(document.scope, ensure_ascii=False)}",
            f"story_position: {json.dumps(document.story_position)}",
            "---",
            "",
            f"# {document.title}",
            "",
            f"- Source: `{document.source_ref}`",
            f"- Snowflake step: {document.snowflake_step}",
            f"- Knowledge class: {document.knowledge_class}",
            "",
            "## Content",
            "",
            document.content.strip(),
            "",
            f"<!-- generated-slug: {slug} -->",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _projection_summary(document: WikiSourceDocument) -> str:
        return one_line(document.content, 180)

    def _write_projection_index(
        self,
        path: Path,
        pages: list[tuple[str, WikiSourceDocument]],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Wiki Index", "", "## Concepts", ""]
        if not pages:
            lines.append("- _No active approved sources._")
        else:
            lines.extend(
                (
                    f"- [[concepts/{slug}|{document.title.replace('|', '-')}]]"
                    f" - {document.knowledge_class} step {document.snowflake_step};"
                    f" `{document.source_ref}`"
                )
                for slug, document in pages
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _score_document(document: WikiSourceDocument, query: WikiContextQuery) -> int:
        tokens = set(re.findall(r"[\w]+", f"{query.instruction} {query.scope}".lower()))
        if not tokens:
            return 0
        title = document.title.lower()
        content = document.content.lower()
        metadata = f"{document.source_ref} {document.artifact_type} {document.scope}".lower()
        score = 0
        for token in tokens:
            if token in title:
                score += 4
            if token in content:
                score += 2
            if token in metadata:
                score += 1
        return score

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
