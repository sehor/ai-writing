"""Analysis application service (P1-04): run once per input, replay after.

Generation is executed through a caller-supplied callable so this service
stays provider-agnostic. Successful runs store the created proposal ids;
repeating an unchanged request replays them instead of duplicating data.
An explicit re-run supersedes still-pending proposals from the previous
run of the same input and records a new run version.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable

from pydantic import ValidationError

from app.analysis.consistency import CONSISTENCY_PROCESSOR
from app.analysis.models import AnalysisRun, ConsistencyFinding
from app.models import ManuscriptRevision
from app.review.service import ensure_writeback_proposals_acceptable


@dataclass
class WritebackAnalysisOutcome:
    proposals: list
    run: AnalysisRun
    cached: bool


@dataclass
class ConsistencyAnalysisOutcome:
    findings: list[ConsistencyFinding]
    run: AnalysisRun
    cached: bool


def compute_input_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return sha256(canonical.encode("utf-8")).hexdigest()


def writeback_input_fingerprint(
    revision: ManuscriptRevision,
    *,
    canon_entities: list | tuple = (),
    memory_records: list | tuple = (),
    extra: dict | None = None,
) -> dict:
    """Deterministic description of every input that can change the
    generated proposals: the revision text plus the canon/memory context
    it is generated against.
    """
    payload = {
        "content": revision.content,
        "title": revision.title,
        "version": revision.version,
        "canon": sorted(
            f"{entity.entity_type}:{entity.name}:v{entity.version}" for entity in canon_entities
        ),
        "memory": sorted(record.title for record in memory_records),
    }
    if extra:
        payload.update(extra)
    return payload


class AnalysisService:
    def __init__(self, data_store):
        self.data_store = data_store

    def run_writeback_generation(
        self,
        *,
        project_id: str,
        source_ref: str,
        processor: str,
        fingerprint: dict,
        generate: Callable[[], list],
        force: bool = False,
        extra_result: dict | None = None,
        supersede_all_pending_for_source: bool = False,
    ) -> WritebackAnalysisOutcome:
        """Generate write-back proposals at most once per exact input.

        The 'generate' callable must return WritebackProposalCreate items
        and may raise; failures are recorded on the run row and retried on
        the next request. 'extra_result' is merged into the stored result
        so callers (P1-05 canon extraction) can persist parse warnings.
        'supersede_all_pending_for_source' extends a forced re-run to every
        still-pending proposal of the same source_ref, not only those of
        the previous run with identical input.
        """
        input_hash = compute_input_hash(fingerprint)
        if not force:
            replayed = self._replay(project_id, source_ref, processor, input_hash)
            if replayed is not None:
                proposals, run = replayed
                return WritebackAnalysisOutcome(proposals=proposals, run=run, cached=True)

        try:
            candidates = list(generate())
            ensure_writeback_proposals_acceptable(self.data_store, project_id, candidates)
        except Exception as exc:
            with self.data_store.connect() as connection:
                self.data_store.record_analysis_run(
                    connection,
                    project_id=project_id,
                    source_ref=source_ref,
                    processor=processor,
                    input_hash=input_hash,
                    status="failed",
                    result_json={"error": f"{type(exc).__name__}: {exc}"},
                )
            raise

        with self.data_store.connect() as connection:
            if force:
                prior = self.data_store.get_analysis_run(
                    project_id, source_ref, processor, input_hash=input_hash
                )
                if prior is not None and prior.status == "succeeded":
                    self._supersede_prior_proposals(connection, prior)
                if supersede_all_pending_for_source:
                    self.data_store.supersede_pending_writebacks_for_source(
                        connection,
                        project_id=project_id,
                        source_ref=source_ref,
                    )
            created = self.data_store.create_writeback_proposals(
                project_id, candidates, connection=connection
            )
            result_json = {"proposal_ids": [proposal.id for proposal in created]}
            if extra_result:
                result_json.update(extra_result)
            run = self.data_store.record_analysis_run(
                connection,
                project_id=project_id,
                source_ref=source_ref,
                processor=processor,
                input_hash=input_hash,
                status="succeeded",
                result_json=result_json,
            )
        return WritebackAnalysisOutcome(proposals=created, run=run, cached=False)

    def run_consistency_analysis(
        self,
        *,
        project_id: str,
        source_ref: str,
        fingerprint: dict,
        check: Callable[[], list],
        force: bool = False,
    ) -> ConsistencyAnalysisOutcome:
        """Run the deterministic consistency checker once per exact input.

        Findings are stored on the run row itself (no proposals are created),
        so a cached replay deserialises them instead of re-checking. Failed
        checks are recorded and retried on the next request.
        """
        input_hash = compute_input_hash(fingerprint)
        if not force:
            replayed = self._replay_findings(project_id, source_ref, input_hash)
            if replayed is not None:
                findings, run = replayed
                return ConsistencyAnalysisOutcome(findings=findings, run=run, cached=True)

        try:
            findings = list(check())
        except Exception as exc:
            with self.data_store.connect() as connection:
                self.data_store.record_analysis_run(
                    connection,
                    project_id=project_id,
                    source_ref=source_ref,
                    processor=CONSISTENCY_PROCESSOR,
                    input_hash=input_hash,
                    status="failed",
                    result_json={"error": f"{type(exc).__name__}: {exc}"},
                )
            raise

        payload = {"findings": [finding.model_dump(mode="json") for finding in findings]}
        with self.data_store.connect() as connection:
            run = self.data_store.record_analysis_run(
                connection,
                project_id=project_id,
                source_ref=source_ref,
                processor=CONSISTENCY_PROCESSOR,
                input_hash=input_hash,
                status="succeeded",
                result_json=payload,
            )
        return ConsistencyAnalysisOutcome(findings=findings, run=run, cached=False)

    def latest_consistency_run(self, project_id: str, source_ref: str) -> AnalysisRun | None:
        return self.data_store.get_analysis_run(project_id, source_ref, CONSISTENCY_PROCESSOR)

    def _replay_findings(self, project_id: str, source_ref: str, input_hash: str):
        run = self.data_store.get_analysis_run(
            project_id, source_ref, CONSISTENCY_PROCESSOR, input_hash=input_hash
        )
        if run is None or run.status != "succeeded":
            return None
        try:
            findings = [
                ConsistencyFinding.model_validate(item)
                for item in run.result_json.get("findings", [])
            ]
        except (ValidationError, AttributeError, TypeError):
            # Stored result no longer parses; regenerate instead of failing.
            return None
        return findings, run

    def _replay(self, project_id: str, source_ref: str, processor: str, input_hash: str):
        run = self.data_store.get_analysis_run(
            project_id, source_ref, processor, input_hash=input_hash
        )
        if run is None or run.status != "succeeded":
            return None
        proposal_ids = run.result_json.get("proposal_ids", [])
        proposals = [
            proposal
            for proposal in (
                self.data_store.get_writeback_proposal(project_id, proposal_id)
                for proposal_id in proposal_ids
            )
            if proposal is not None
        ]
        if len(proposals) != len(proposal_ids):
            # The stored result no longer resolves; regenerate instead of
            # returning a partial answer. An empty successful proposal set is
            # still a complete cached result and must not re-run an external
            # compiler/provider for unchanged input.
            return None
        return proposals, run

    def _supersede_prior_proposals(self, connection, prior: AnalysisRun) -> None:
        for proposal_id in prior.result_json.get("proposal_ids", []):
            connection.execute(
                """
                UPDATE writeback_proposals
                SET status = 'superseded'
                WHERE project_id = ? AND id = ? AND status = 'pending_review'
                """,
                (prior.project_id, proposal_id),
            )
