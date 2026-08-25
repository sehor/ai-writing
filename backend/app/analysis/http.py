"""HTTP helpers that surface analysis outcomes without changing bodies."""

from typing import Protocol

from fastapi import Depends, Response

from app.analysis.service import AnalysisService
from app.data import WritingDataStore, get_data_store


def get_analysis_service(
    data_store: WritingDataStore = Depends(get_data_store),
) -> AnalysisService:
    return AnalysisService(data_store=data_store)


class AnalysisOutcome(Protocol):
    """Minimal shape shared by every analysis outcome."""

    @property
    def cached(self) -> bool: ...

    @property
    def run(self): ...


def apply_analysis_headers(response: Response, outcome: AnalysisOutcome) -> None:
    response.headers["X-Analysis-Cached"] = "true" if outcome.cached else "false"
    response.headers["X-Analysis-Run-Id"] = outcome.run.id
    response.headers["X-Analysis-Run-Version"] = str(outcome.run.run_version)
