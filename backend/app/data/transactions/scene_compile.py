"""Scene compile flows; the caller owns commit/rollback on the shared connection."""

import sqlite3

from app.data.helpers import utc_now
from app.data.repositories.manuscript import ManuscriptRepository
from app.data.repositories.scene_proposals import (
    SceneChapterMissingError,
    SceneProposalNotFoundError,
    SceneProposalQualityError,
    SceneProposalRepository,
    SceneProposalReviewedError,
    SceneSequenceConflictError,
    scene_contract_input,
)
from app.data.repositories.scenes import SceneRepository
from app.data.repositories.snowflake_records import SnowflakeRecordRepository
from app.models import SceneContract, SceneContractUpdate, SceneProposal


def accept_scene_proposals(
    connection: sqlite3.Connection,
    *,
    project_id: str,
    proposal_ids: list[str],
) -> tuple[list[SceneContract], list[SceneProposal]]:
    """Batch-accept pending proposals into scene contracts.

    One transaction creates every contract and marks every proposal
    accepted; any validation failure raises before a single insert,
    and an insert failure rolls the whole batch back.
    """
    proposals_repo = SceneProposalRepository(connection)
    scenes_repo = SceneRepository(connection)
    chapters_repo = ManuscriptRepository(connection)

    proposals = [proposals_repo.get(project_id, pid) for pid in proposal_ids]
    missing = [pid for pid, proposal in zip(proposal_ids, proposals) if proposal is None]
    if missing:
        raise SceneProposalNotFoundError(missing[0])

    blocked = [
        proposal for proposal in proposals if proposal.status not in ("pending_review", "accepted")
    ]
    if blocked:
        # Rejected / superseded proposals are terminal; accepting
        # them would violate the unified review state machine.
        first = blocked[0]
        raise SceneProposalReviewedError(
            f"Scene proposal '{first.id}' is already reviewed "
            f"(status '{first.status}'); accepting it again is not allowed."
        )

    ordered = sorted(
        (proposal for proposal in proposals if proposal.status == "pending_review"),
        key=lambda proposal: (proposal.sequence, proposal.id),
    )
    already_accepted = [proposal for proposal in proposals if proposal.status == "accepted"]

    # Pre-validation before any insert so nothing partial is written.
    chapter_ids = {chapter.id for chapter in chapters_repo.list_chapters(project_id)}
    seen_sequences: dict[int, str] = {}
    for proposal in ordered:
        if proposal.blocking_errors:
            raise SceneProposalQualityError(
                f"Scene proposal '{proposal.id}' is blocked: " + "; ".join(proposal.blocking_errors)
            )
        if proposal.sequence in seen_sequences:
            raise SceneSequenceConflictError(
                f"Proposals '{seen_sequences[proposal.sequence]}' and "
                f"'{proposal.id}' both use scene sequence {proposal.sequence}."
            )
        seen_sequences[proposal.sequence] = proposal.id
        if proposal.chapter_id and proposal.chapter_id not in chapter_ids:
            raise SceneChapterMissingError(
                f"Scene proposal '{proposal.id}' references chapter "
                f"'{proposal.chapter_id}', which does not belong to this project."
            )

    target_ids = set()
    for proposal in ordered:
        if proposal.source_record_id:
            head = SnowflakeRecordRepository(connection).get_head(
                project_id, 8, proposal.source_record_id
            )
            if head is None or head.accepted_revision_id != proposal.source_record_revision_id:
                raise SceneProposalReviewedError(
                    "Source record changed; recompile and review the latest proposal."
                )
            linked = scenes_repo.get_by_source(project_id, proposal.source_record_id)
            if proposal.operation == "create" and linked is not None:
                raise SceneProposalReviewedError(
                    "Source record already has a scene; recompile before accepting."
                )
        if proposal.operation == "update":
            target = scenes_repo.get(project_id, proposal.target_scene_id)
            if (
                target is None
                or target.source_record_id != proposal.source_record_id
                or target.plan_version != proposal.expected_plan_version
                or target.id in target_ids
            ):
                raise SceneProposalReviewedError(
                    "Target scene plan changed; recompile and review the latest differences."
                )
            target_ids.add(target.id)
    existing_sequences = {
        scene.sequence for scene in scenes_repo.list(project_id) if scene.id not in target_ids
    }
    clashes = sorted(set(seen_sequences) & existing_sequences)
    if clashes:
        raise SceneSequenceConflictError(
            "Scene sequence already exists for this project: "
            + ", ".join(str(number) for number in clashes)
            + "."
        )

    now = utc_now()
    created_scenes = []
    # Vacate target sequence slots to permit atomic swaps/reordering.
    for index, scene_id in enumerate(sorted(target_ids)):
        connection.execute(
            "UPDATE scene_contracts SET sequence = ? WHERE project_id = ? AND id = ?",
            (-100000 - index, project_id, scene_id),
        )
    for proposal in ordered:
        desired = scene_contract_input(proposal)
        if proposal.operation == "update":
            scene = scenes_repo.update(
                project_id, proposal.target_scene_id, SceneContractUpdate(**desired.model_dump())
            )
        else:
            scene = scenes_repo.insert(project_id, desired)
        if proposal.source_record_id:
            scenes_repo.bind_source(
                project_id, scene.id, proposal.source_record_id, proposal.source_record_revision_id
            )
            scene = scenes_repo.get(project_id, scene.id)
        created_scenes.append(scene)
        updated = proposals_repo.mark_accepted(
            project_id=project_id,
            proposal_id=proposal.id,
            applied_scene_id=scene.id,
            reviewed_at=now,
        )
        if updated == 0:
            raise SceneProposalReviewedError(
                f"Scene proposal '{proposal.id}' changed concurrently."
            )

    accepted_ids = [proposal.id for proposal in ordered]
    accepted_ids.extend(proposal.id for proposal in already_accepted)
    accepted = [proposals_repo.get(project_id, pid) for pid in accepted_ids]
    replayed_scenes = [
        scenes_repo.get(project_id, proposal.applied_scene_id)
        for proposal in already_accepted
        if proposal.applied_scene_id
    ]
    scenes = created_scenes + [scene for scene in replayed_scenes if scene]
    return scenes, [proposal for proposal in accepted if proposal is not None]
