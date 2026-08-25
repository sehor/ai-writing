"""Rules for applying write-back proposals to existing records.

Pure domain logic: no HTTP, no database. The data layer calls
``apply_canon_update`` inside its accept transaction; proposal creation
routes call ``validate_update_proposal`` before anything is persisted.
"""

from app.models import CanonEntity, WritebackProposalCreate

UPDATABLE_CANON_FIELDS: frozenset[str] = frozenset(
    {
        "entity_type",
        "name",
        "summary",
        "current_state",
        "constraints",
        "last_seen",
        "timeline_notes",
    }
)

CANON_ENTITY_TYPES: frozenset[str] = frozenset({"character", "location", "item", "faction", "rule"})


class WritebackApplyError(ValueError):
    """A write-back proposal could not be applied to its target record."""


class WritebackTargetMissingError(WritebackApplyError):
    def __init__(self, target_record_id: str):
        self.target_record_id = target_record_id
        super().__init__(f"Write-back target record '{target_record_id}' no longer exists.")


class WritebackVersionConflictError(WritebackApplyError):
    def __init__(self, target_record_id: str, expected_version: int | None, actual_version: int):
        self.target_record_id = target_record_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Canon record '{target_record_id}' changed since the proposal was "
            f"created (expected version {expected_version}, current version {actual_version})."
        )


def validate_update_proposal(proposal: WritebackProposalCreate) -> None:
    """Structural validation for ``action='update'`` write-back proposals.

    Raises ValueError with a precise message; creation routes map that to
    HTTP 422 so invalid proposals never reach the database.
    """
    if proposal.target != "canon_entity":
        raise ValueError(
            f"Update write-backs currently support canon_entity targets, "
            f"got target='{proposal.target}'."
        )
    if not proposal.target_record_id:
        raise ValueError("Update write-back proposals require a target_record_id.")
    if proposal.expected_version is None or proposal.expected_version < 1:
        raise ValueError(
            "Update write-back proposals require the expected_version of the target record."
        )
    if not proposal.changes:
        raise ValueError("Update write-back proposals require at least one field change.")

    for field, change in proposal.changes.items():
        if field not in UPDATABLE_CANON_FIELDS:
            raise ValueError(
                f"Cannot update canon field '{field}'; "
                f"updatable fields: {sorted(UPDATABLE_CANON_FIELDS)}."
            )
        after = change.get("after")
        if after is None:
            raise ValueError(f"Change for canon field '{field}' requires an 'after' value.")
        if not isinstance(after, str):
            raise ValueError(f"'after' value for canon field '{field}' must be a string.")
        if field == "entity_type" and after not in CANON_ENTITY_TYPES:
            raise ValueError(
                f"'after' entity_type '{after}' is not one of {sorted(CANON_ENTITY_TYPES)}."
            )
        if field == "name" and not after.strip():
            raise ValueError("'name' cannot be updated to a blank value.")


def apply_canon_update(
    current: CanonEntity,
    proposal: WritebackProposalCreate,
    *,
    new_version: int,
    updated_at: str,
) -> CanonEntity:
    """Return the updated CanonEntity described by an update proposal.

    Callers must have verified the version beforehand.
    """
    updates = {field: str(change.get("after", "")) for field, change in proposal.changes.items()}
    return CanonEntity(
        **{
            **current.model_dump(),
            **updates,
            "version": new_version,
            "updated_at": updated_at,
        }
    )
