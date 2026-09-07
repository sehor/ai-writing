from fastapi import Depends, HTTPException, status

from app.data import WritingDataStore, get_data_store
from app.analysis.service import AnalysisService
from app.cognition.registry import CognitionRegistry, get_cognition_registry
from app.llm import ModelRuntime
from app.llm_wiki.dependencies import get_llm_wiki
from app.llm_wiki.interfaces import LlmWiki
from app.agents.snowflake_workflow import SnowflakeWorkflow
from app.agents.writing_workflow import LocalDraftWritingWorkflow, WritingWorkflow
from app.services.compile_service import CompileService
from app.services.manuscript_service import ManuscriptService
from app.services.model_service import ModelService
from app.services.reference_service import ReferenceService
from app.services.writeback_service import WritebackService
from app.services.snowflake_service import (
    SNOWFLAKE_STEPS,
    SnowflakeService,
    SelectableWritingWorkflow,
)


def require_project(project_id: str, data_store: WritingDataStore) -> None:
    if not data_store.project_exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )


def get_analysis_service(
    data_store: WritingDataStore = Depends(get_data_store),
) -> AnalysisService:
    return AnalysisService(data_store=data_store)


def get_compile_service(
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> CompileService:
    return CompileService(data_store, cognition)


def get_manuscript_service(
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> ManuscriptService:
    return ManuscriptService(data_store, cognition)


def get_writeback_service(
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
    analysis: AnalysisService = Depends(get_analysis_service),
) -> WritebackService:
    return WritebackService(data_store, cognition, analysis)


def get_reference_service(
    data_store: WritingDataStore = Depends(get_data_store),
    cognition: CognitionRegistry = Depends(get_cognition_registry),
) -> ReferenceService:
    return ReferenceService(data_store, cognition)


def get_model_service(
    data_store: WritingDataStore = Depends(get_data_store),
) -> ModelService:
    return ModelService(data_store)


def get_snowflake_service(
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> SnowflakeService:
    return SnowflakeService(data_store, llm_wiki)


def get_writing_workflow(
    data_store: WritingDataStore = Depends(get_data_store),
    llm_wiki: LlmWiki = Depends(get_llm_wiki),
) -> WritingWorkflow:
    """Route explicit model selections remotely and preserve default local fallback."""
    runtime = ModelRuntime(recorder=data_store)
    return SelectableWritingWorkflow(
        local=LocalDraftWritingWorkflow(data_store, SNOWFLAKE_STEPS, llm_wiki),
        remote=SnowflakeWorkflow(data_store, SNOWFLAKE_STEPS, runtime, llm_wiki),
        runtime=runtime,
    )
