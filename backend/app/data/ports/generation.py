from __future__ import annotations

from typing import Protocol

from app.models import (
    GenerationAttempt,
    GenerationAttemptCreate,
    GenerationRun,
    GenerationRunCreate,
    GenerationRunUpdate,
)


class GenerationRecorder(Protocol):
    def add_generation_attempt(
        self, run_id: str, create: GenerationAttemptCreate
    ) -> GenerationAttempt: ...

    def create_generation_run(self, create: GenerationRunCreate) -> GenerationRun: ...

    def finish_generation_run(self, run_id: str, update: GenerationRunUpdate) -> None: ...


class GenerationRunReader(Protocol):
    def get_generation_run(self, project_id: str, run_id: str) -> GenerationRun | None: ...

    def list_generation_runs(self, project_id: str, limit: int = 100) -> list[GenerationRun]: ...
