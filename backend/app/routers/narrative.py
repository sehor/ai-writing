from fastapi import APIRouter, Depends, HTTPException, status
from app.narrative.director import DirectorAnalyzer, DirectorReport

from app.data import WritingDataStore, get_data_store
from app.dependencies import require_project
from app.models import (
    CharacterKnowledge,
    NarrativeRelation,
    CharacterKnowledgeCreate,
    StoryFact,
    StoryFactCreate,
    StoryStateResponse,
    StoryThread,
    StoryThreadCreate,
    StoryThreadEvent,
    StoryThreadEventCreate,
    StoryThreadStatusUpdate,
)


router = APIRouter(tags=["narrative"])


@router.get("/projects/{project_id}/narrative/relations", response_model=list[NarrativeRelation])
def list_narrative_relations(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[NarrativeRelation]:
    require_project(project_id, data_store)
    return data_store.list_narrative_relations(project_id)


@router.get("/projects/{project_id}/narrative/director", response_model=DirectorReport | None)
def narrative_director(
    project_id: str,
    scene_id: str = "",
    data_store: WritingDataStore = Depends(get_data_store),
) -> DirectorReport | None:
    require_project(project_id, data_store)
    if not scene_id:
        scenes = data_store.list_scene_contracts(project_id)
        if not scenes:
            return None
        scene_id = max(scenes, key=lambda scene: scene.sequence).id
    if data_store.get_scene_contract(project_id, scene_id) is None:
        raise HTTPException(status_code=404, detail="Scene contract not found.")
    return DirectorAnalyzer(data_store).for_scene(project_id=project_id, scene_id=scene_id)


@router.get("/projects/{project_id}/story-facts", response_model=list[StoryFact])
def list_story_facts(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[StoryFact]:
    require_project(project_id, data_store)
    return data_store.list_story_facts(project_id)


@router.post(
    "/projects/{project_id}/story-facts",
    response_model=StoryFact,
    status_code=status.HTTP_201_CREATED,
)
def create_story_fact(
    project_id: str,
    fact: StoryFactCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> StoryFact:
    require_project(project_id, data_store)
    try:
        return data_store.create_story_fact(project_id, fact)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.put(
    "/projects/{project_id}/story-facts/{fact_id}/character-knowledge",
    response_model=CharacterKnowledge,
)
def set_character_knowledge(
    project_id: str,
    fact_id: str,
    knowledge: CharacterKnowledgeCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> CharacterKnowledge:
    require_project(project_id, data_store)
    try:
        return data_store.set_character_knowledge(project_id, fact_id, knowledge)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/projects/{project_id}/story-state", response_model=StoryStateResponse)
def get_story_state(
    project_id: str,
    scene_position: int,
    character: str = "",
    data_store: WritingDataStore = Depends(get_data_store),
) -> StoryStateResponse:
    require_project(project_id, data_store)
    world_truth = data_store.list_story_facts_at(project_id, scene_position)
    reader_knowledge = data_store.list_reader_facts_at(project_id, scene_position)
    character_knowledge = (
        data_store.list_character_facts_at(project_id, character, scene_position)
        if character.strip()
        else []
    )
    return StoryStateResponse(
        project_id=project_id,
        scene_position=scene_position,
        character=character.strip(),
        world_truth=world_truth,
        reader_knowledge=reader_knowledge,
        character_knowledge=character_knowledge,
    )


@router.get("/projects/{project_id}/story-threads", response_model=list[StoryThread])
def list_story_threads(
    project_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[StoryThread]:
    require_project(project_id, data_store)
    return data_store.list_story_threads(project_id)


@router.post(
    "/projects/{project_id}/story-threads",
    response_model=StoryThread,
    status_code=status.HTTP_201_CREATED,
)
def create_story_thread(
    project_id: str,
    thread: StoryThreadCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> StoryThread:
    require_project(project_id, data_store)
    try:
        return data_store.create_story_thread(project_id, thread)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.put(
    "/projects/{project_id}/story-threads/{thread_id}/status",
    response_model=StoryThread,
)
def update_story_thread_status(
    project_id: str,
    thread_id: str,
    update: StoryThreadStatusUpdate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> StoryThread:
    require_project(project_id, data_store)
    thread = data_store.update_story_thread_status(project_id, thread_id, update)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story thread not found.")
    return thread


@router.get(
    "/projects/{project_id}/story-threads/{thread_id}/events",
    response_model=list[StoryThreadEvent],
)
def list_story_thread_events(
    project_id: str,
    thread_id: str,
    data_store: WritingDataStore = Depends(get_data_store),
) -> list[StoryThreadEvent]:
    require_project(project_id, data_store)
    return data_store.list_story_thread_events(project_id, thread_id)


@router.post(
    "/projects/{project_id}/story-threads/{thread_id}/events",
    response_model=StoryThreadEvent,
    status_code=status.HTTP_201_CREATED,
)
def add_story_thread_event(
    project_id: str,
    thread_id: str,
    event: StoryThreadEventCreate,
    data_store: WritingDataStore = Depends(get_data_store),
) -> StoryThreadEvent:
    require_project(project_id, data_store)
    if data_store.get_scene_contract(project_id, event.scene_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Scene contract not found."
        )
    try:
        return data_store.add_story_thread_event(project_id, thread_id, event)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
