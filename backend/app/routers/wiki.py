from fastapi import APIRouter, Depends, HTTPException, status

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import (
    LlmWiki,
    WikiContextQuery,
    WikiContextResult,
    WikiInsightQuery,
    WikiInsightResult,
)


router = APIRouter(tags=["wiki"])


def require_matching_project(project_id: str, request_project_id: str) -> None:
    if project_id != request_project_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Wiki request project_id must match the route project_id.",
        )


@router.post(
    "/projects/{project_id}/wiki/context",
    response_model=WikiContextResult,
)
def retrieve_wiki_context(
    project_id: str,
    query: WikiContextQuery,
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> WikiContextResult:
    require_project(project_id, data_store)
    require_matching_project(project_id, query.project_id)
    return llm_wiki.retrieve_context(query)


@router.post(
    "/projects/{project_id}/wiki/insights",
    response_model=WikiInsightResult,
)
def generate_wiki_insights(
    project_id: str,
    query: WikiInsightQuery,
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> WikiInsightResult:
    require_project(project_id, data_store)
    require_matching_project(project_id, query.project_id)
    return llm_wiki.analyze(query)
