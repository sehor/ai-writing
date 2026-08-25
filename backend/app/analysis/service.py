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

from app.analysis.models import AnalysisRun
from app.models import ManuscriptRevision
from app.review.service import ensure_writeback_proposals_acceptable


@dataclass
class WritebackAnalysisOutcome:
    proposals: list
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
    ) -> WritebackAnalysisOutcome:
        """Generate write-back proposals at most once per exact input.

        ``generate`` must return ``WritebackProposalCreate`` items and may
        raise; failures are recorded on the run row and retried on the
        next request.
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
            created = self.data_store.create_writeback_proposals(
                project_id, candidates, connection=connection
            )
            run = self.data_store.record_analysis_run(
                connection,
                project_id=project_id,
                source_ref=source_ref,
                processor=processor,
                input_hash=input_hash,
                status="succeeded",
                result_json={"proposal_ids": [proposal.id for proposal in created]},
            )
        return WritebackAnalysisOutcome(proposals=created, run=run, cached=False)

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
        if len(proposals) != len(proposal_ids) or not proposals:
            # The stored result no longer resolves; regenerate instead of
            # returning a partial answer.
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
