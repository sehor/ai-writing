"""Compatibility shim: the scene-proposal errors moved to repositories.

routers.snowflake imports these exception classes from this module path,
so they are re-exported from their new home. All proposal SQL now lives
in app.data.repositories.scene_proposals.
"""

from app.data.repositories.scene_proposals import (
    SceneChapterMissingError,
    SceneProposalNotFoundError,
    SceneProposalReviewedError,
    SceneSequenceConflictError,
)

__all__ = [
    "SceneChapterMissingError",
    "SceneProposalNotFoundError",
    "SceneProposalReviewedError",
    "SceneSequenceConflictError",
]
