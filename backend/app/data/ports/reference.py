from __future__ import annotations

from typing import Protocol
from app.models import ManuscriptScene, ManuscriptProposal

from app.data.ports.generation import GenerationRecorder
from app.data.ports.reading import NarrativeSnapshotReader, ProjectSnapshotReader
from app.models import ReferenceSuggestion, ReferenceSuggestionCreate, ReferenceSuggestionStatus


class ReferenceDataPort(
    ProjectSnapshotReader, NarrativeSnapshotReader, GenerationRecorder, Protocol
):
    def get_manuscript_scene(self, project_id: str, scene_id: str) -> ManuscriptScene | None: ...

    def get_manuscript_proposal(
        self, project_id: str, proposal_id: str
    ) -> ManuscriptProposal | None: ...

    def create_reference_suggestion(
        self, project_id: str, suggestion: ReferenceSuggestionCreate
    ) -> ReferenceSuggestion: ...

    def list_reference_suggestions(self, project_id: str) -> list[ReferenceSuggestion]: ...

    def update_reference_suggestion_status(
        self, project_id: str, suggestion_id: str, suggestion_status: ReferenceSuggestionStatus
    ) -> ReferenceSuggestion | None: ...
