"""Review application service.

One place that knows how a review decision moves through the unified
state machine, how domain violations surface to the shared HTTP
semantics (404 / 409 / 422), and how write-back proposals are gated
before they reach the database.
"""

from fastapi import HTTPException, status

from app.agents.writeback_workflow import validate_writeback_payload
from app.review.state_machine import (
    InvalidReviewTransitionError,
    ReviewStatus,
    validate_review_transition,
)


class WritebackPreValidationError(ValueError):
    """A proposal could never be accepted, so it must not be persisted."""


def decide(current: str, target: str, subject: str = "Record") -> ReviewStatus:
    """Validate a requested review decision and return the effective status."""
    validate_review_transition(current, target, subject)
    return target  # type: ignore[return-value]


def conflict_from(exc: ValueError) -> HTTPException:
    """Map a state-machine or apply violation to HTTP 409 semantics."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


def unprocessable_from(exc: ValueError) -> HTTPException:
    """Map a proposal validation failure to HTTP 422 semantics."""
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def ensure_writeback_proposals_acceptable(data_store, project_id: str, proposals) -> None:
    """P1-03 gate: every proposal is checked against current data *before*
    insertion, so anything that gets created can later be accepted unless
    the underlying data changes concurrently.
    """
    for proposal in proposals:
        try:
            validate_writeback_payload(proposal)
        except ValueError as exc:
            raise WritebackPreValidationError(str(exc)) from exc
        if proposal.target == "story_thread_status":
            _ensure_story_thread_target_current(data_store, project_id, proposal)
        elif proposal.target == "story_thread":
            title = str(proposal.payload.get("title", "")).strip().lower()
            if any(thread.title.strip().lower() == title for thread in data_store.list_story_threads(project_id)):
                raise WritebackPreValidationError(
                    f"Create proposal '{proposal.title}' duplicates an existing StoryThread."
                )
        elif proposal.target == "story_thread_event" and proposal.target_record_id:
            if not any(
                thread.id == proposal.target_record_id
                for thread in data_store.list_story_threads(project_id)
            ):
                raise WritebackPreValidationError(
                    f"Event proposal '{proposal.title}' targets a missing StoryThread."
                )
        elif proposal.action == "update":
            _ensure_update_target_current(data_store, project_id, proposal)
        elif proposal.target == "canon_entity":
            _ensure_canon_create_target_available(data_store, project_id, proposal)


def _ensure_update_target_current(data_store, project_id: str, proposal) -> None:
    entity = data_store.get_canon_entity(project_id, proposal.target_record_id)
    if entity is None:
        raise WritebackPreValidationError(
            f"Update proposal '{proposal.title}' targets canon record "
            f"'{proposal.target_record_id}', which does not exist."
        )
    if entity.version != proposal.expected_version:
        raise WritebackPreValidationError(
            f"Update proposal '{proposal.title}' expects canon record "
            f"'{entity.name}' at version {proposal.expected_version}, but the "
            f"current version is {entity.version}."
        )


def _ensure_story_thread_target_current(data_store, project_id: str, proposal) -> None:
    thread = next(
        (
            item
            for item in data_store.list_story_threads(project_id)
            if item.id == proposal.target_record_id
        ),
        None,
    )
    if thread is None:
        raise WritebackPreValidationError(
            f"Lifecycle proposal '{proposal.title}' targets StoryThread "
            f"'{proposal.target_record_id}', which does not exist."
        )
    expected = str(proposal.payload.get("from_state", ""))
    if thread.status != expected:
        raise WritebackPreValidationError(
            f"Lifecycle proposal '{proposal.title}' expects StoryThread '{thread.id}' "
            f"at status '{expected}', but the current status is '{thread.status}'."
        )


def _ensure_canon_create_target_available(data_store, project_id: str, proposal) -> None:
    name = str(proposal.payload.get("name", "")).strip().lower()
    entity_type = str(proposal.payload.get("entity_type", "")).strip().lower()
    if not name or not entity_type:
        return  # malformed payloads are rejected by validate_writeback_payload
    for entity in data_store.list_canon_entities(project_id):
        if entity.entity_type == entity_type and entity.name.strip().lower() == name:
            raise WritebackPreValidationError(
                f"Create proposal '{proposal.title}' duplicates existing canon "
                f"{entity_type} '{entity.name}' ({entity.id}); accepting it would "
                "violate the unique-name rule."
            )


__all__ = [
    "InvalidReviewTransitionError",
    "WritebackPreValidationError",
    "conflict_from",
    "decide",
    "ensure_writeback_proposals_acceptable",
    "unprocessable_from",
]
