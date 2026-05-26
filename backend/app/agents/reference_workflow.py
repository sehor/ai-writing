from app.agents.deepseek_workflow import DeepSeekSettings
from app.agents.writing_workflow import WorkflowNotConfiguredError
from app.cognition.interfaces import ContextPacket, ProjectCognitionSnapshot, WritingScope
from app.models import (
    CanonEntity,
    MemoryRecord,
    ReferenceGenerationRequest,
    ReferenceSuggestionCreate,
    SceneContract,
    WorkflowAgentTrace,
)


def build_reference_context(
    snapshot: ProjectCognitionSnapshot,
    request: ReferenceGenerationRequest,
    cognition_context: list[ContextPacket],
) -> str:
    sections = [
        "Reference generation context. The output is advisory and must not commit project state.",
        "",
        "## Project",
        f"Title: {snapshot.project.title}",
        f"Premise: {snapshot.project.premise}",
        f"Current Snowflake step: {snapshot.project.current_step}",
        "",
        "## Request",
        f"Suggestion type: {request.suggestion_type}",
        f"Scope: {request.scope_type}:{request.scope_ref or 'project'}",
        f"Author problem: {request.author_problem}",
        f"Desired output: {request.desired_output or 'No specific output format requested.'}",
        "",
        "## Active Scope",
        describe_scope(snapshot, request),
        "",
        "## Canon Constraints",
        format_canon(snapshot.canon_entities),
        "",
        "## Memory / Style",
        format_memory(snapshot.memory_records),
        "",
        "## Recent Manuscript",
        "\n\n".join(
            f"### {scene.title} v{scene.version}\n{truncate(scene.content, 1200)}"
            for scene in snapshot.manuscript_scenes[:6]
        )
        or "No accepted manuscript scenes recorded.",
        "",
        "## Cognition Context",
        format_cognition(cognition_context),
    ]
    return "\n".join(sections)


def build_local_reference_suggestion(
    request: ReferenceGenerationRequest,
    context: str,
    snapshot: ProjectCognitionSnapshot,
    cognition_context: list[ContextPacket],
) -> ReferenceSuggestionCreate:
    scope_label = f"{request.scope_type}:{request.scope_ref or snapshot.project.id}"
    title = f"{reference_type_title(request.suggestion_type)} for {scope_label}"
    trace = [
        WorkflowAgentTrace(
            stage="pre_generation",
            agent_name="reference_context_loader",
            status="assembled project, Canon, Memory, manuscript, and cognition context",
        ),
        WorkflowAgentTrace(
            stage="generation",
            agent_name="local_reference_generator",
            status="drafted deterministic reference options",
        ),
        WorkflowAgentTrace(
            stage="post_generation",
            agent_name="reference_guardrail_reviewer",
            status="kept output advisory; no project state committed",
        ),
    ]
    return ReferenceSuggestionCreate(
        suggestion_type=request.suggestion_type,
        scope_type=request.scope_type,
        scope_ref=request.scope_ref,
        title=title,
        content=build_local_reference_content(request, snapshot),
        rationale=(
            "Generated as a non-committing reference to help the author move past a blocked writing step. "
            "Use it as source material for a later reviewed manuscript or write-back proposal."
        ),
        used_context=context,
        canon_warnings=build_canon_warnings(request, snapshot.canon_entities, snapshot.scenes),
        style_notes=build_style_notes(snapshot.memory_records),
        graph_warnings=build_graph_warnings(cognition_context),
        proposed_writebacks=[],
        workflow_trace=trace,
    )


def build_provider_reference_suggestion(
    settings: DeepSeekSettings,
    request: ReferenceGenerationRequest,
    context: str,
    snapshot: ProjectCognitionSnapshot,
    cognition_context: list[ContextPacket],
) -> ReferenceSuggestionCreate:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise WorkflowNotConfiguredError(
            "The OpenAI-compatible SDK is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc

    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
    response = client.chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You generate advisory reference material for AI Writing Studio. "
                    "Help a fiction author get unstuck without committing project state. "
                    "Respect Canon as confirmed fact. Treat Memory / Style as prose continuity guidance. "
                    "If facts are missing, mark assumptions as options or TBD. Return Markdown only."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(
                    [
                        "Generate a concise, reviewable reference suggestion for this blocked writing task.",
                        "",
                        context,
                    ]
                ),
            },
        ],
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
    content = response.choices[0].message.content if response.choices else ""
    if not content:
        raise ValueError("empty provider response")

    suggestion = build_local_reference_suggestion(request, context, snapshot, cognition_context)
    return suggestion.model_copy(
        update={
            "title": f"{suggestion.title} provider draft",
            "content": content.strip(),
            "workflow_trace": [
                *suggestion.workflow_trace[:1],
                WorkflowAgentTrace(
                    stage="generation",
                    agent_name="deepseek_reference_generator",
                    status=f"called {settings.model}",
                ),
                suggestion.workflow_trace[-1],
            ],
        }
    )


def scope_for_request(request: ReferenceGenerationRequest) -> WritingScope:
    return WritingScope(
        kind=request.scope_type,
        ref=request.scope_ref or "project",
        instruction=request.author_problem,
    )


def describe_scope(
    snapshot: ProjectCognitionSnapshot,
    request: ReferenceGenerationRequest,
) -> str:
    if request.scope_type == "snowflake_step" and request.scope_ref:
        artifact = next(
            (item for item in snapshot.artifacts if str(item.step_number) == request.scope_ref),
            None,
        )
        if artifact:
            return f"Snowflake step {artifact.step_number} `{artifact.artifact}`:\n{truncate(artifact.content, 2000)}"
    if request.scope_type == "scene" and request.scope_ref:
        scene = next((item for item in snapshot.scenes if item.id == request.scope_ref), None)
        if scene:
            return "\n".join(
                [
                    f"Scene {scene.sequence}: {scene.title}",
                    f"POV: {scene.pov or 'unset'}",
                    f"Goal: {scene.goal or 'unset'}",
                    f"Conflict: {scene.conflict or 'unset'}",
                    f"Turning point: {scene.turning_point or 'unset'}",
                    f"Required Canon: {scene.required_canon or 'unset'}",
                    f"Forbidden facts: {scene.forbidden_facts or 'unset'}",
                    f"Open threads: {scene.open_threads or 'none'}",
                ]
            )
    if request.scope_type == "canon_entity" and request.scope_ref:
        entity = next((item for item in snapshot.canon_entities if item.id == request.scope_ref), None)
        if entity:
            return f"{entity.entity_type}: {entity.name}\nState: {entity.current_state}\nConstraints: {entity.constraints}"
    if request.scope_type == "memory_record" and request.scope_ref:
        record = next((item for item in snapshot.memory_records if item.id == request.scope_ref), None)
        if record:
            return f"{record.record_type}: {record.title}\nScope: {record.scope}\n{truncate(record.content, 2000)}"
    if request.scope_type == "manuscript_scene" and request.scope_ref:
        scene = next((item for item in snapshot.manuscript_scenes if item.scene_id == request.scope_ref), None)
        if scene:
            return f"{scene.title} v{scene.version}\n{truncate(scene.content, 2000)}"
    return "Project-level reference generation."


def build_local_reference_content(
    request: ReferenceGenerationRequest,
    snapshot: ProjectCognitionSnapshot,
) -> str:
    premise = snapshot.project.premise
    problem = request.author_problem
    output = request.desired_output or "usable next-step options"
    return "\n".join(
        [
            f"# {reference_type_title(request.suggestion_type)}",
            "",
            "## Working Frame",
            f"- Current block: {problem}",
            f"- Desired output: {output}",
            f"- Project premise: {premise}",
            "",
            "## Reference Options",
            "1. **Clarify the immediate dramatic question.** State what the reader should wonder in this unit, then choose the option that makes the next scene unavoidable.",
            "2. **Push one confirmed constraint harder.** Pick a Canon constraint and turn it into pressure, cost, or withheld information instead of inventing a new fact.",
            "3. **Use an open thread as movement.** Convert one unresolved question into a concrete action, clue, refusal, or reversal.",
            "",
            "## Candidate Next Move",
            build_candidate_next_move(request),
            "",
            "## Review Before Saving",
            "- Treat this as reference material, not committed manuscript.",
            "- Check every named fact against Canon before using it.",
            "- If this implies new Canon or Memory, create a separate write-back proposal after human review.",
        ]
    )


def build_candidate_next_move(request: ReferenceGenerationRequest) -> str:
    if request.suggestion_type == "scene_bridge":
        return "Write a short bridging beat that starts from the last accepted action, introduces one obstacle, and exits on a changed decision."
    if request.suggestion_type == "conflict_options":
        return "List three escalating conflicts: practical opposition, relational cost, and forbidden-information pressure."
    if request.suggestion_type == "character_motivation":
        return "Give the POV character one visible goal, one private fear, and one choice that reveals both without exposition."
    if request.suggestion_type == "canon_gap":
        return "Mark missing facts as TBD and propose only questions the author must answer before drafting."
    if request.suggestion_type == "prose_reference":
        return "Draft a small style sample that preserves Memory / Style patterns while avoiding new confirmed facts."
    if request.suggestion_type == "structure_fix":
        return "Choose one graph risk or open thread and propose where it should be advanced, delayed, or intentionally left unresolved."
    return "Generate three compact alternatives, then pick the one that best preserves Canon and creates a clearer next action."


def build_canon_warnings(
    request: ReferenceGenerationRequest,
    canon_entities: list[CanonEntity],
    scenes: list[SceneContract],
) -> list[str]:
    warnings: list[str] = []
    if not canon_entities:
        warnings.append("No Canon entities are recorded; keep all new facts tentative until reviewed.")
    if request.scope_type == "scene" and request.scope_ref:
        scene = next((item for item in scenes if item.id == request.scope_ref), None)
        if scene and not scene.required_canon:
            warnings.append("The selected scene has no required Canon constraints recorded.")
        if scene and scene.forbidden_facts:
            warnings.append(f"Respect forbidden facts for this scene: {scene.forbidden_facts}")
    return warnings


def build_style_notes(memory_records: list[MemoryRecord]) -> list[str]:
    if not memory_records:
        return ["No Memory / Style records are available; keep prose samples neutral and provisional."]
    return [
        f"Use `{record.title}` as {record.record_type} guidance for scope `{record.scope or 'global'}`."
        for record in memory_records[:4]
    ]


def build_graph_warnings(cognition_context: list[ContextPacket]) -> list[str]:
    warnings: list[str] = []
    for packet in cognition_context:
        if packet.module == "llm_wiki" and "## Structure Notes" in packet.content:
            warnings.append("Review LLM Wiki structure notes for unresolved threads and isolated entities.")
        if packet.module == "memplace":
            warnings.append("Review Memplace continuity context before turning reference text into manuscript.")
    return warnings


def format_canon(entities: list[CanonEntity]) -> str:
    if not entities:
        return "No Canon entities recorded."
    return "\n".join(
        f"- {entity.entity_type}: {entity.name} | state={truncate(entity.current_state, 400)} | constraints={truncate(entity.constraints, 400)}"
        for entity in entities[:30]
    )


def format_memory(records: list[MemoryRecord]) -> str:
    if not records:
        return "No Memory / Style records recorded."
    return "\n\n".join(
        f"### {record.record_type}: {record.title}\nScope: {record.scope or 'global'}\n{truncate(record.content, 1000)}"
        for record in records[:12]
    )


def format_cognition(packets: list[ContextPacket]) -> str:
    if not packets:
        return "No cognition module context available."
    return "\n\n".join(
        f"### {packet.module}: {packet.title}\n{truncate(packet.content, 2200)}"
        for packet in packets
    )


def reference_type_title(suggestion_type: str) -> str:
    return suggestion_type.replace("_", " ").title()


def truncate(value: str, limit: int) -> str:
    compact = value.strip()
    if len(compact) <= limit:
        return compact or "None."
    return f"{compact[: limit - 3].rstrip()}..."
