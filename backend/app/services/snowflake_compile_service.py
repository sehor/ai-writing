"""Structured Snowflake compiler service (P1-05).

Orchestrates the two record-authoritative compile paths from the improvement plan:

- Step 7: accepted Character Bible records -> Canon create / update
  write-back proposals (reviewed through the existing write-back flow).
- Step 8: accepted Scene List records -> persisted Scene
  Proposals with parse warnings, batch-accepted into scene contracts.

Both paths are idempotent through the P1-04 analysis_runs table: an
unchanged input replays stored proposals instead of duplicating them,
and an explicit re-run supersedes stale pending proposals.
"""

from dataclasses import dataclass
import re

from app.analysis.service import AnalysisService, compute_input_hash
from app.data import WritingDataStore
from app.models import (
    CanonExtractionReport,
    SceneContract,
    SceneParseReport,
    SceneProposal,
    SceneProposalCreate,
    SceneProposalStatus,
    WritebackProposalCreate,
)
from app.snowflake_compiler import (
    CANON_EXTRACT_STEP,
    SCENE_PARSE_STEP,
    ArtifactNotParseableError,
    extract_canon_record_proposals,
    parse_scene_records,
)


CANON_EXTRACTOR_PROCESSOR = "local_canon_extractor"
SCENE_PARSER_PROCESSOR = "local_scene_parser"
THREAD_ACTION_RE = re.compile(
    r"^(plant|reinforce|misdirect|escalate|partial_payoff|payoff)\s*[:|\-]\s*(.+)$",
    re.IGNORECASE,
)


@dataclass
class _RunInfo:
    run_id: str
    run_version: int
    cached: bool


def _canon_fingerprint(entities) -> list[str]:
    return sorted(f"{entity.entity_type}:{entity.name}:v{entity.version}" for entity in entities)


def _canon_candidate_key(proposal) -> tuple:
    """Stable identity of a parsed canon proposal for dedupe checks."""
    if proposal.action == "update":
        return (
            "update",
            proposal.target_record_id,
            tuple(
                sorted(
                    (field, change.get("after", "")) for field, change in proposal.changes.items()
                )
            ),
        )
    return (
        "create",
        str(proposal.payload.get("entity_type", "")).strip().lower(),
        str(proposal.payload.get("name", "")).strip().lower(),
    )


class SnowflakeCompileService:
    def __init__(self, data_store: WritingDataStore):
        self.data_store = data_store
        self.analysis = AnalysisService(data_store)

    # ------------------------------------------------------------------
    # Step 7: canon extraction
    # ------------------------------------------------------------------

    def extract_canon_proposals(
        self,
        project_id: str,
        step_number: int = CANON_EXTRACT_STEP,
        *,
        force: bool = False,
    ) -> CanonExtractionReport:
        records = self.data_store.list_accepted_snowflake_records(project_id, step_number)
        if not records:
            raise LookupError(
                f"Snowflake step {step_number} has no accepted records to compile."
            )

        canon_entities = self.data_store.list_canon_entities(project_id)
        source_ref = f"snowflake_records:{project_id}:{step_number}"
        fingerprint = {
            "records": [
                {
                    "record_id": record.record_id,
                    "revision_id": record.id,
                    "position": record.position,
                    "payload": record.payload,
                }
                for record in records
            ],
            "canon": _canon_fingerprint(canon_entities),
            "step": step_number,
        }

        def _generate() -> list:
            extraction = extract_canon_record_proposals(
                records,
                canon_entities,
                source_ref=source_ref,
            )
            # The holder list is shared with extra_result below, so the
            # warnings are persisted on the very same run row.
            warnings_holder.extend(extraction.warnings)
            if force:
                # A forced re-run supersedes every pending proposal of this
                # source inside the accept transaction, so nothing here can
                # be a duplicate afterwards.
                return extraction.proposals

            # Idempotency guard: an identical proposal that is still
            # pending for this accepted record set must not be created twice, even
            # when the Canon context changed enough to miss the cached
            # run (for example right after accepting a sibling proposal).
            pending_keys = {
                _canon_candidate_key(proposal)
                for proposal in self.data_store.list_writeback_proposals(project_id)
                if proposal.status == "pending_review" and proposal.source_ref == source_ref
            }
            fresh = []
            for proposal in extraction.proposals:
                if _canon_candidate_key(proposal) in pending_keys:
                    warnings_holder.append(
                        f"Proposal '{proposal.title}' is already pending review; "
                        "skipped as a duplicate."
                    )
                    continue
                fresh.append(proposal)
            return fresh

        warnings_holder: list[str] = []
        outcome = self.analysis.run_writeback_generation(
            project_id=project_id,
            source_ref=source_ref,
            processor=CANON_EXTRACTOR_PROCESSOR,
            fingerprint=fingerprint,
            generate=_generate,
            force=force,
            extra_result={"warnings": warnings_holder},
            supersede_all_pending_for_source=force,
        )
        return CanonExtractionReport(
            project_id=project_id,
            step_number=step_number,
            processor=CANON_EXTRACTOR_PROCESSOR,
            cached=outcome.cached,
            run_id=outcome.run.id,
            run_version=outcome.run.run_version,
            warnings=self._stored_warnings(
                outcome.run.result_json, outcome.cached, warnings_holder
            ),
            proposals=outcome.proposals,
        )

    # ------------------------------------------------------------------
    # Step 8: scene parsing
    # ------------------------------------------------------------------

    def parse_scene_proposals(
        self,
        project_id: str,
        step_number: int = SCENE_PARSE_STEP,
        *,
        force: bool = False,
    ) -> SceneParseReport:
        records = self.data_store.list_accepted_snowflake_records(project_id, step_number)
        if not records:
            raise LookupError(
                f"Snowflake step {step_number} has no accepted records to compile."
            )

        source_ref = f"snowflake_records:{project_id}:{step_number}"
        fingerprint = {
            "records": [
                {
                    "record_id": record.record_id,
                    "revision_id": record.id,
                    "position": record.position,
                    "payload": record.payload,
                }
                for record in records
            ],
            "canon": _canon_fingerprint(self.data_store.list_canon_entities(project_id)),
            "step": step_number,
        }
        input_hash = compute_input_hash(fingerprint)

        if not force:
            replayed = self._replay_scene_run(project_id, source_ref, input_hash)
            if replayed is not None:
                proposals, run = replayed
                return SceneParseReport(
                    project_id=project_id,
                    step_number=step_number,
                    processor=SCENE_PARSER_PROCESSOR,
                    cached=True,
                    run_id=run.id,
                    run_version=run.run_version,
                    warnings=run.result_json.get("warnings", []),
                    proposals=proposals,
                    thread_proposals=[
                        proposal
                        for proposal_id in run.result_json.get("thread_proposal_ids", [])
                        if (proposal := self.data_store.get_writeback_proposal(project_id, proposal_id))
                        is not None
                    ],
                )

        try:
            outcome = parse_scene_records(
                records,
                canon_entities=self.data_store.list_canon_entities(project_id),
            )
        except ArtifactNotParseableError:
            # Record the failed attempt; nothing was written anywhere else.
            with self.data_store.connect() as connection:
                self.data_store.record_analysis_run(
                    connection,
                    project_id=project_id,
                    source_ref=source_ref,
                    processor=SCENE_PARSER_PROCESSOR,
                    input_hash=input_hash,
                    status="failed",
                    result_json={"error": "ArtifactNotParseableError"},
                )
            raise

        creates = [
            SceneProposalCreate(
                sequence=scene.sequence,
                chapter_id=getattr(scene, "resolved_chapter_id", ""),
                chapter_hint=scene.chapter_hint,
                title=scene.title,
                pov=scene.pov,
                goal=scene.goal,
                conflict=scene.conflict,
                turning_point=scene.turning_point,
                outcome=scene.outcome,
                required_canon_ids=",".join(getattr(scene, "resolved_canon_ids", [])),
                required_canon_raw="\n".join(scene.required_canon_names),
                forbidden_fact_refs=scene.forbidden_fact_refs,
                information_delta=scene.information_delta,
                character_state_delta=scene.character_state_delta,
                story_thread_actions=scene.story_thread_actions,
                open_threads=scene.open_threads,
                source_ref=source_ref,
                source_excerpt=scene.source_excerpt,
                warnings=scene.warnings,
                blocking_errors=scene.blocking_errors,
            )
            for scene in outcome.scenes
        ]
        known_thread_titles = {
            thread.title.strip().lower()
            for thread in self.data_store.list_story_threads(project_id)
        }
        for create in creates:
            for raw in create.story_thread_actions.splitlines():
                match = THREAD_ACTION_RE.match(raw.strip())
                if (
                    match
                    and match.group(1).lower() != "plant"
                    and match.group(2).strip().lower() not in known_thread_titles
                ):
                    create.blocking_errors.append(
                        f"StoryThread '{match.group(2).strip()}' must exist before "
                        f"the '{match.group(1).lower()}' action can be accepted."
                    )

        with self.data_store.connect() as connection:
            if force:
                self.data_store.supersede_pending_scene_proposals(
                    connection,
                    project_id=project_id,
                    source_ref=source_ref,
                )
            created = self.data_store.create_scene_proposals(
                project_id, creates, connection=connection
            )
            thread_creates = self._thread_proposal_creates(project_id, created)
            thread_proposals = self.data_store.create_writeback_proposals(
                project_id, thread_creates, connection=connection
            )
            run = self.data_store.record_analysis_run(
                connection,
                project_id=project_id,
                source_ref=source_ref,
                processor=SCENE_PARSER_PROCESSOR,
                input_hash=input_hash,
                status="succeeded",
                result_json={
                    "proposal_ids": [proposal.id for proposal in created],
                    "thread_proposal_ids": [proposal.id for proposal in thread_proposals],
                    "warnings": outcome.warnings,
                },
            )

        return SceneParseReport(
            project_id=project_id,
            step_number=step_number,
            processor=SCENE_PARSER_PROCESSOR,
            cached=False,
            run_id=run.id,
            run_version=run.run_version,
            warnings=outcome.warnings,
            proposals=created,
            thread_proposals=thread_proposals,
        )

    def _thread_proposal_creates(
        self, project_id: str, scenes: list[SceneProposal]
    ) -> list[WritebackProposalCreate]:
        existing = {
            thread.title.strip().lower(): thread
            for thread in self.data_store.list_story_threads(project_id)
        }
        proposed_titles: set[str] = set()
        result: list[WritebackProposalCreate] = []
        for scene in scenes:
            for raw in scene.story_thread_actions.splitlines():
                match = THREAD_ACTION_RE.match(raw.strip())
                if not match:
                    continue
                action = match.group(1).lower()
                title = match.group(2).strip()
                key = title.lower()
                thread = existing.get(key)
                if thread is None and action != "plant":
                    continue
                if thread is None and key not in proposed_titles:
                    result.append(
                        WritebackProposalCreate(
                            target="story_thread",
                            action="create",
                            title=f"Create StoryThread: {title}",
                            rationale=f"Step 8 scene {scene.sequence} references this thread.",
                            source_ref=scene.source_ref,
                            payload={
                                "thread_type": "foreshadow",
                                "title": title,
                                "status": "planned",
                                "planted_at": scene.sequence if action == "plant" else None,
                                "importance": 3,
                                "reveal_constraints": "",
                            },
                        )
                    )
                    proposed_titles.add(key)
                result.append(
                    WritebackProposalCreate(
                        target="story_thread_event",
                        action="create",
                        title=f"{action.replace('_', ' ').title()} thread: {title}",
                        rationale=f"Step 8 scene {scene.sequence} proposes a thread event.",
                        source_ref=scene.source_ref,
                        target_record_id=thread.id if thread else "",
                        payload={
                            "thread_title": title,
                            "scene_id": scene.id,
                            "scene_proposal_id": scene.id,
                            "action": action,
                            "note": scene.source_excerpt,
                        },
                    )
                )
        return result

    # ------------------------------------------------------------------
    # Review of parsed scene proposals
    # ------------------------------------------------------------------

    def list_scene_proposals(self, project_id: str) -> list[SceneProposal]:
        return self.data_store.list_scene_proposals(project_id)

    def update_scene_proposal_status(
        self,
        project_id: str,
        proposal_id: str,
        new_status: SceneProposalStatus,
    ) -> SceneProposal | None:
        return self.data_store.update_scene_proposal_status(project_id, proposal_id, new_status)

    def accept_scene_proposals(
        self,
        project_id: str,
        proposal_ids: list[str],
    ) -> tuple[list[SceneContract], list[SceneProposal]]:
        return self.data_store.accept_scene_proposals(project_id, proposal_ids)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _replay_scene_run(self, project_id: str, source_ref: str, input_hash: str):
        run = self.data_store.get_analysis_run(
            project_id, source_ref, SCENE_PARSER_PROCESSOR, input_hash=input_hash
        )
        if run is None or run.status != "succeeded":
            return None
        proposal_ids = run.result_json.get("proposal_ids", [])
        proposals = [
            proposal
            for proposal in (
                self.data_store.get_scene_proposal(project_id, proposal_id)
                for proposal_id in proposal_ids
            )
            if proposal is not None
        ]
        if len(proposals) != len(proposal_ids) or not proposals:
            # The stored result no longer resolves; regenerate instead of
            # returning a partial answer.
            return None
        return proposals, run

    def _stored_warnings(self, result_json: dict, cached: bool, fresh: list[str]) -> list[str]:
        if not cached:
            return list(fresh)
        stored = result_json.get("warnings", [])
        return list(stored) if isinstance(stored, list) else []


__all__ = [
    "CANON_EXTRACTOR_PROCESSOR",
    "SCENE_PARSER_PROCESSOR",
    "SnowflakeCompileService",
]
