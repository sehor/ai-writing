"""Single source of truth for review status transitions.

Every reviewable object (manuscript proposals, write-back proposals,
reference suggestions) shares the same states and the same rules:

    pending_review -> accepted | rejected | superseded

Leaving a decided state is forbidden. Repeating the current state is an
idempotent no-op, not a transition.
"""

from typing import Literal

ReviewStatus = Literal["pending_review", "accepted", "rejected", "superseded"]

PENDING_REVIEW: ReviewStatus = "pending_review"
ACCEPTED: ReviewStatus = "accepted"
REJECTED: ReviewStatus = "rejected"
SUPERSEDED: ReviewStatus = "superseded"

REVIEW_TRANSITIONS: dict[str, frozenset[str]] = {
    PENDING_REVIEW: frozenset({ACCEPTED, REJECTED, SUPERSEDED}),
    ACCEPTED: frozenset(),
    REJECTED: frozenset(),
    SUPERSEDED: frozenset(),
}


class InvalidReviewTransitionError(ValueError):
    """A review status change violated the unified state machine.

    Routers and services map this to the shared HTTP 409 semantics
    ("already reviewed; the decision cannot be changed").
    """

    def __init__(self, current: str, target: str, subject: str = "Record"):
        self.current = current
        self.target = target
        self.subject = subject
        super().__init__(
            f"{subject} is already reviewed (status '{current}'); "
            f"changing it to '{target}' is not allowed."
        )


def is_terminal_review_status(status: str) -> bool:
    """True once a record can no longer move to any other status."""
    return not REVIEW_TRANSITIONS.get(status)


def validate_review_transition(current: str, target: str, subject: str = "Record") -> None:
    """Raise InvalidReviewTransitionError for an illegal transition.

    Repeating the current status is allowed as an idempotent no-op;
    callers return the unchanged record in that case.
    """
    if current == target:
        return
    if target in REVIEW_TRANSITIONS.get(current, frozenset()):
        return
    raise InvalidReviewTransitionError(current, target, subject)
