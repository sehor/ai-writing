"""Deterministic Scene Contract compilers for Snowflake Step 8.

Accepted records are the authoritative production input. The Markdown parser remains
a compatibility helper and enforces the same required scene fields as the records.
Pure domain logic: no HTTP, no database, no provider calls.

Recognized block shape (the local deterministic draft and the DeepSeek
output contract both produce this):

    ### Scene 1: The Glass City
    - POV: Mira Vale
    - Goal: ...
    - Conflict: ...
    - Turning point: ...
    - Outcome: ...
    - Required Canon: Mira Vale; Glass City
    - Forbidden facts: ...
    - Open threads: ...
    - Chapter hint: Chapter 2

Structural validation blocks missing pov/goal/conflict/turning_point/outcome,
duplicate or out-of-range sequences, unresolved canon references and
unresolved chapter hints as warnings; nothing here raises except a
completely unparseable artifact.
"""

from dataclasses import dataclass, field
import json
import re

from app.models import SnowflakeRecordRevision
from app.snowflake.contracts import SceneListRecord
from app.snowflake_compiler.errors import ArtifactNotParseableError
from app.text_utils import truncate as truncate_text


SCENE_HEADER_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(?:scene|场景)\s*#?(?P<number>\d+)\s*"
    r"(?:[::\-—–|]\s*(?P<rest>.*?))?(?:\*\*)?\s*$",
    re.IGNORECASE,
)
SCENE_FIELD_RE = re.compile(
    r"^\s*[-*•]?\s*(?:\*\*)?(?P<label>pov|goal|conflict|turning point|outcome|disaster|"
    r"required canon|required|forbidden facts?|forbidden fact refs|"
    r"information delta|character state delta|(?:story\s*)?thread actions?|"
    r"open threads?|chapter(?:\s+hint)?|title)\s*(?:\*\*)?\s*[::]\s*(?P<value>.*)$",
    re.IGNORECASE,
)
TBD_VALUE_RE = re.compile(r"^(?:tbd|tba|n/?a)[.!?]?$", re.IGNORECASE)
CHAPTER_NUMBER_RE = re.compile(r"^(?:chapter\s*)?(?P<number>\d+)$", re.IGNORECASE)

FIELD_LIMITS = {
    "title": 160,
    "pov": 120,
    "goal": 1000,
    "conflict": 1000,
    "turning_point": 1000,
    "outcome": 1000,
}

LIST_SPLIT_RE = re.compile(r"[;;、]|\n")


@dataclass
class ParsedScene:
    """One parsed scene block before persistence."""

    sequence: int
    title: str
    pov: str = ""
    goal: str = ""
    conflict: str = ""
    turning_point: str = ""
    outcome: str = ""
    required_canon_names: list[str] = field(default_factory=list)
    forbidden_fact_refs: str = ""
    information_delta: str = ""
    character_state_delta: str = ""
    story_thread_actions: str = ""
    open_threads: str = ""
    chapter_hint: str = ""
    source_excerpt: str = ""
    warnings: list[str] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)
    resolved_canon_ids: list[str] = field(default_factory=list)
    resolved_chapter_id: str = ""


@dataclass
class SceneParseOutcome:
    scenes: list[ParsedScene]
    warnings: list[str]


def parse_scene_artifact(
    content: str,
    *,
    canon_entities: list = (),
    chapters: list = (),
) -> SceneParseOutcome:
    """Parse a Step 8 artifact into scene drafts with warnings.

    canon_entities and chapters are the project's current records; they
    resolve required-canon names to ids and chapter hints to chapter ids.
    Raises ArtifactNotParseableError when no scene block exists.
    """
    blocks, _scan_warnings = _split_scene_blocks(content)
    if not blocks:
        raise ArtifactNotParseableError(
            "No 'Scene N' blocks could be parsed from the Step 8 artifact. "
            "Expected headers like '### Scene 1: Title' with "
            "'- POV / - Goal / - Conflict / - Turning point' bullets."
        )

    canon_by_name = {
        entity.name.strip().lower(): entity
        for entity in canon_entities
        if getattr(entity, "name", "").strip()
    }
    chapters_by_title: dict[str, object] = {}
    chapters_by_sequence: dict[int, object] = {}
    for chapter in chapters:
        title = getattr(chapter, "title", "").strip().lower()
        if title:
            chapters_by_title.setdefault(title, chapter)
        sequence = getattr(chapter, "sequence", None)
        if isinstance(sequence, int):
            chapters_by_sequence.setdefault(sequence, chapter)

    scenes: list[ParsedScene] = []
    for number, rest, lines in blocks:
        scenes.append(_build_scene(number, rest, lines))

    _resolve_sequences(scenes)
    global_warnings = _validate_structure(scenes)

    for scene in scenes:
        resolved_ids: list[str] = []
        unresolved: list[str] = []
        for name in scene.required_canon_names:
            entity = canon_by_name.get(name.strip().lower())
            if entity is None:
                unresolved.append(name.strip())
            else:
                resolved_ids.append(entity.id)
        if unresolved:
            scene.blocking_errors.append(
                f"Scene {scene.sequence}: required Canon references not present "
                f"in the Canon DB: {', '.join(unresolved)}."
            )
        scene.resolved_canon_ids = resolved_ids

        hint = scene.chapter_hint.strip()
        if hint:
            chapter = _match_chapter(hint, chapters_by_title, chapters_by_sequence)
            if chapter is None:
                scene.warnings.append(
                    f"Scene {scene.sequence}: chapter hint '{hint}' did not match "
                    "any existing chapter."
                )
            else:
                scene.resolved_chapter_id = getattr(chapter, "id", "")

    return SceneParseOutcome(scenes=scenes, warnings=global_warnings)


def parse_scene_records(
    records: list[SnowflakeRecordRevision],
    *,
    canon_entities: list = (),
) -> SceneParseOutcome:
    """Compile accepted Step 8 record heads without consulting a blob Artifact."""
    if not records:
        raise ArtifactNotParseableError(
            "No accepted Step 8 Scene List records are available to compile."
        )
    canon_by_id = {entity.id: entity for entity in canon_entities}
    scenes: list[ParsedScene] = []
    seen_sequences: set[int] = set()
    thread_action_map = {
        "open": "plant",
        "advance": "reinforce",
        "complicate": "escalate",
        "payoff": "payoff",
        "close": "payoff",
    }
    for record in records:
        payload = SceneListRecord.model_validate(record.payload)
        actions = "\n".join(
            f"{thread_action_map[action.action]}: {action.description}"
            for action in payload.story_thread_actions
        )
        scene = ParsedScene(
            sequence=record.position,
            title=payload.what_happens[:160],
            pov=payload.pov_character_id,
            goal=payload.goal,
            conflict=payload.conflict,
            turning_point=payload.turning_point,
            outcome=f"{payload.outcome}: {payload.exit_condition}",
            required_canon_names=list(payload.required_canon_refs),
            forbidden_fact_refs="\n".join(payload.forbidden_fact_refs),
            information_delta="\n".join(payload.information_delta),
            character_state_delta="\n".join(payload.character_state_delta),
            story_thread_actions=actions,
            source_excerpt=truncate_text(
                json.dumps(record.payload, ensure_ascii=False, sort_keys=True), 1200
            ),
        )
        missing_canon_ids = [
            canon_id for canon_id in payload.required_canon_refs if canon_id not in canon_by_id
        ]
        if missing_canon_ids:
            scene.blocking_errors.append(
                f"Scene record '{record.record_id}' references missing Canon IDs: "
                + ", ".join(missing_canon_ids)
                + "."
            )
        scene.resolved_canon_ids = [
            canon_id for canon_id in payload.required_canon_refs if canon_id in canon_by_id
        ]
        if record.position in seen_sequences:
            scene.blocking_errors.append(
                f"Scene record '{record.record_id}' duplicates sequence {record.position}."
            )
        if record.position > 999:
            scene.blocking_errors.append(
                f"Scene record '{record.record_id}' exceeds the maximum sequence of 999."
            )
        seen_sequences.add(record.position)
        scenes.append(scene)
    warnings = _validate_structure(scenes)
    return SceneParseOutcome(scenes=scenes, warnings=warnings)


def _split_scene_blocks(content: str) -> tuple[list[tuple[int, str, list[str]]], list[str]]:
    """Return ([(number, header_title_text, body_lines)], warnings)."""
    blocks: list[tuple[int, str, list[str]]] = []
    current_number: int | None = None
    current_rest = ""
    current_lines: list[str] = []

    def finalize() -> None:
        nonlocal current_number, current_lines
        if current_number is not None:
            blocks.append((current_number, current_rest, current_lines))
        current_number = None
        current_lines = []

    for raw_line in content.splitlines():
        header = SCENE_HEADER_RE.match(raw_line)
        if header:
            finalize()
            current_number = int(header.group("number"))
            current_rest = (header.group("rest") or "").strip()
            current_lines = [raw_line]
            continue
        if current_number is not None:
            current_lines.append(raw_line)
    finalize()
    return blocks, []


def _build_scene(number: int, header_rest: str, lines: list[str]) -> ParsedScene:
    label = f"Scene {number}"
    scene = ParsedScene(sequence=number, title="")
    fields: dict[str, str] = {}
    last_field: str | None = None

    for raw_line in lines[1:]:
        match = SCENE_FIELD_RE.match(raw_line)
        if match:
            label_normalized = match.group("label").strip().lower()
            value = match.group("value").strip()
            if TBD_VALUE_RE.match(value):
                scene.warnings.append(
                    f"{label}: field '{match.group('label').strip()}' is marked TBD."
                )
                value = ""
            key = _field_key(label_normalized)
            if key is None:
                continue
            existing = fields.get(key, "")
            fields[key] = f"{existing}\n{value}".strip() if existing else value
            last_field = key
            continue
        stripped = raw_line.strip()
        if (
            stripped
            and not stripped.startswith(("#", "-", "*", "•"))
            and not SCENE_HEADER_RE.match(stripped)
            and last_field
        ):
            fields[last_field] = truncate_text(f"{fields[last_field]}\n{stripped}".strip(), 4000)

    # Title precedence: an explicit '- Title:' bullet beats header text.
    title = (fields.get("title") or "").strip() or header_rest.strip()
    if not title:
        title = label
        scene.warnings.append(f"{label}: no title found; using the default '{label}'.")
    scene.title = truncate_text(title.strip().lstrip("#*- ").strip(), FIELD_LIMITS["title"])
    scene.pov = truncate_text(fields.get("pov", "").strip(), FIELD_LIMITS["pov"])
    scene.goal = truncate_text(fields.get("goal", "").strip(), FIELD_LIMITS["goal"])
    scene.conflict = truncate_text(fields.get("conflict", "").strip(), FIELD_LIMITS["conflict"])
    scene.turning_point = truncate_text(
        fields.get("turning_point", "").strip(), FIELD_LIMITS["turning_point"]
    )
    scene.outcome = truncate_text(fields.get("outcome", "").strip(), FIELD_LIMITS["outcome"])
    scene.required_canon_names = _split_list(fields.get("required_canon", ""))
    scene.forbidden_fact_refs = truncate_text(
        "\n".join(_split_list(fields.get("forbidden_facts", ""))), 4000
    )
    scene.information_delta = truncate_text(fields.get("information_delta", "").strip(), 4000)
    scene.character_state_delta = truncate_text(
        fields.get("character_state_delta", "").strip(), 4000
    )
    scene.story_thread_actions = truncate_text(
        "\n".join(_split_list(fields.get("story_thread_actions", ""))), 4000
    )
    scene.open_threads = truncate_text("\n".join(_split_list(fields.get("open_threads", ""))), 4000)
    scene.chapter_hint = truncate_text(fields.get("chapter_hint", "").strip(), 160)
    scene.source_excerpt = truncate_text("\n".join(lines).strip(), 1200)
    return scene


def _field_key(label: str) -> str | None:
    if label == "pov":
        return "pov"
    if label == "goal":
        return "goal"
    if label == "conflict":
        return "conflict"
    if label == "turning point":
        return "turning_point"
    if label in {"outcome", "disaster"}:
        return "outcome"
    if label in {"required canon", "required"}:
        return "required_canon"
    if label in {"forbidden facts", "forbidden fact", "forbidden fact refs"}:
        return "forbidden_facts"
    if label == "information delta":
        return "information_delta"
    if label == "character state delta":
        return "character_state_delta"
    if label in {
        "thread action",
        "thread actions",
        "storythread action",
        "storythread actions",
        "story thread action",
        "story thread actions",
    }:
        return "story_thread_actions"
    if label in {"open threads", "open thread"}:
        return "open_threads"
    if label in {"chapter", "chapter hint"}:
        return "chapter_hint"
    if label == "title":
        return "title"
    return None


def _split_list(value: str) -> list[str]:
    items: list[str] = []
    for chunk in LIST_SPLIT_RE.split(value):
        cleaned = chunk.strip().lstrip("-*• ").strip()
        if cleaned:
            items.append(cleaned)
    return items


def _resolve_sequences(scenes: list[ParsedScene]) -> None:
    """Keep author numbering; fix duplicates and values below 1."""
    used: set[int] = set()
    next_free = 1
    for scene in scenes:
        candidate = scene.sequence
        if candidate < 1 or candidate in used:
            while next_free in used or next_free < 1:
                next_free += 1
            scene.warnings.append(
                f"Scene number {candidate} was duplicated or invalid; re-sequenced to {next_free}."
            )
            candidate = next_free
        used.add(candidate)
        next_free = max(next_free, candidate) + 1
        scene.sequence = candidate


def _validate_structure(scenes: list[ParsedScene]) -> list[str]:
    warnings: list[str] = []
    for scene in scenes:
        missing = [
            name
            for name in (
                "pov",
                "goal",
                "conflict",
                "turning_point",
                "outcome",
                "information_delta",
                "character_state_delta",
            )
            if not getattr(scene, name).strip()
        ]
        if missing:
            scene.blocking_errors.append(
                f"Scene {scene.sequence} ({scene.title}) is missing: {', '.join(missing)}."
            )
        valid_thread_actions = {
            "plant",
            "reinforce",
            "misdirect",
            "escalate",
            "partial_payoff",
            "payoff",
        }
        for raw_action in scene.story_thread_actions.splitlines():
            action, separator, title = raw_action.partition(":")
            if not separator:
                action, separator, title = raw_action.partition("|")
            if not separator:
                action, separator, title = raw_action.partition("-")
            if action.strip().lower() not in valid_thread_actions or not title.strip():
                scene.blocking_errors.append(
                    f"Scene {scene.sequence} has invalid StoryThread action '{raw_action}'; "
                    "use action: thread title."
                )
    over_limit = [scene.sequence for scene in scenes if scene.sequence > 999]
    if over_limit:
        warnings.append(
            "Scene numbers exceed the maximum sequence of 999: "
            + ", ".join(str(number) for number in over_limit)
            + "; they must be renumbered before acceptance."
        )
    return warnings


def _match_chapter(hint: str, by_title: dict, by_sequence: dict):
    chapter = by_title.get(hint.strip().lower())
    if chapter is not None:
        return chapter
    numbered = CHAPTER_NUMBER_RE.match(hint.strip())
    if numbered:
        return by_sequence.get(int(numbered.group("number")))
    return None
