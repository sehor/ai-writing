"""HTTP headers that surface analysis outcomes without changing bodies."""

from fastapi import Response

from app.analysis.service import WritebackAnalysisOutcome


def apply_analysis_headers(response: Response, outcome: WritebackAnalysisOutcome) -> None:
    response.headers["X-Analysis-Cached"] = "true" if outcome.cached else "false"
    response.headers["X-Analysis-Run-Id"] = outcome.run.id
    response.headers["X-Analysis-Run-Version"] = str(outcome.run.run_version)
