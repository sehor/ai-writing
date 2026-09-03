"""Deterministic Canon extractor for Snowflake Step 7 artifacts (P1-05).

Parses the saved character-bible artifact into Canon create / update
write-back proposals. Pure domain logic: no HTTP, no database, no
provider calls, so parse failures can never touch persistence.

Accepted block shapes (mixed freely):

    ### Character: Mira Vale
    - Type: character
    - Summary: ...
    - Current state: ...
    - Constraints: ...
    - Last seen: Act II
    - Timeline notes: ...

    ## Location: Glass City
    Summary text runs directly under the heading.

Unparseable input raises ArtifactNotParseableError before any proposal
exists; partially valid blocks produce warnings and are skipped.
"""

from dataclasses import dataclass, field
import re

from pydantic import ValidationError

from app.models import CanonEntity, CanonEntityCreate, WritebackProposalCreate
from app.snowflake_compiler.errors import ArtifactNotParseableError
from app.text_utils import truncate as truncate_text


# Field limits copied from CanonEntityCreate so parsed values never fail
# validation later (P1-03: proposals must be acceptable when created).
FIELD_LIMITS: dict[str, int] = {
    "entity_type": 60,
    "name": 120,
    "summary": 1000,
    "current_state": 4000,
    "constraints": 4000,
    "last_seen": 120,
    "timeline_notes": 8000,
    "confirmed": 20,
}

TYPE_ALIASES: dict[str, str] = {
    "character": "character",
    "characters": "character",
    "location": "location",
    "locations": "location",
    "place": "location",
    "city": "location",
    "item": "item",
    "items": "item",
    "object": "item",
    "faction": "faction",
    "factions": "faction",
    "organization": "faction",
    "organisation": "faction",
    "rule": "rule",
    "rules": "rule",
}

FIELD_LABELS: dict[str, str] = {
    "type": "entity_type",
    "entity type": "entity_type",
    "name": "name",
    "summary": "summary",
    "current state": "current_state",
    "state": "current_state",
    "status": "current_state",
    "constraint": "constraints",
    "constraints": "constraints",
    "last seen": "last_seen",
    "last_seen": "last_seen",
    "timeline notes": "timeline_notes",
    "timeline": "timeline_notes",
    "confirmed": "confirmed",
    "canon confirmed": "confirmed",
}

HEADING_RE = re.compile(r"^\s*#{1,6}\s+(?P<header>.*?)\s*$")
BOLD_NAME_RE = re.compile(r"^\s*(?:[-*•]\s*)?\*\*(?P<name>[^*]{1,160})\*\*\s*:?\s*$")
BULLET_FIELD_RE = re.compile(
    r"^\s*[-*•]?\s*(?:\*\*)?(?P<label>[A-Za-z_ ][A-Za-z_ ]{0,30}?)\s*(?:\*\*)?\s*[::]\s*(?P<value>.*)$"
)
TBD_RE = re.compile(r"^(?:tbd|tba|unknown|n/?a)[.!?]?$", re.IGNORECASE)


@dataclass
class CanonEntityDraft:
    entity_type: str
    name: str
    fields: dict[str, str] = field(default_factory=dict)
    source_excerpt: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class CanonExtraction:
    proposals: list[WritebackProposalCreate]
    warnings: list[str]


def extract_canon_proposals(
    content: str,
    existing_entities: list[CanonEntity],
    *,
    source_ref: str,
) -> CanonExtraction:
    """Parse a Step 7 artifact into Canon create / update proposals.

    Raises ArtifactNotParseableError when the artifact holds no
    name-bearing blocks at all.
    """
    drafts = _parse_blocks(content)
    if not drafts:
        raise ArtifactNotParseableError(
            "No character/location/item/faction blocks could be parsed from the "
            "Step 7 artifact. Expected blocks like '### Character: Name' with "
            "'- Field: value' bullets."
        )

    warnings: list[str] = []
    proposals: list[WritebackProposalCreate] = []
    seen_keys: set[tuple[str, str]] = set()
    by_name: dict[str, list[CanonEntity]] = {}
    for entity in existing_entities:
        by_name.setdefault(entity.name.strip().lower(), []).append(entity)

    for draft in drafts:
        label = f"'{draft.name}'" if draft.name else "unnamed block"
        warnings.extend(draft.warnings)

        payload_fields = {
            key: truncate_text(value.strip(), FIELD_LIMITS[key])
            for key, value in draft.fields.items()
        }
        name = payload_fields.get("name", "")
        if not name:
            warnings.append(f"Skipped {label}: no name could be parsed.")
            continue
        entity_type = payload_fields.get("entity_type", draft.entity_type)
        if entity_type not in TYPE_ALIASES.values():
            warnings.append(f"Skipped '{name}': unknown entity type '{entity_type}'.")
            continue
        if payload_fields.get("confirmed", "").strip().lower() not in {"yes", "true", "confirmed"}:
            warnings.append(
                f"Skipped '{name}': Character Bible records become Canon proposals only when "
                "'- Confirmed: yes' is explicit."
            )
            continue

        key = (entity_type, name.strip().lower())
        if key in seen_keys:
            warnings.append(
                f"Skipped duplicate block '{name}' ({entity_type}); the first occurrence wins."
            )
            continue
        seen_keys.add(key)

        try:
            create = CanonEntityCreate(
                entity_type=entity_type,  # type: ignore[arg-type]
                **{
                    field_name: payload_fields.get(field_name, "")
                    for field_name in FIELD_LIMITS
                    if field_name not in {"entity_type", "confirmed"}
                },
            )
        except ValidationError as exc:
            warnings.append(f"Skipped '{name}': invalid canon values ({exc}).")
            continue

        matches = by_name.get(name.strip().lower(), [])
        target = next(
            (entity for entity in matches if entity.entity_type == entity_type),
            matches[0] if matches else None,
        )
        if target is None:
            proposals.append(_build_create_proposal(create, source_ref, draft.source_excerpt))
            continue
        update = _build_update_proposal(create, target, source_ref, draft.source_excerpt)
        if update is None:
            warnings.append(f"'{target.name}' already matches the artifact; no update needed.")
            continue
        proposals.append(update)

    return CanonExtraction(proposals=proposals, warnings=warnings)


def _parse_blocks(content: str) -> list[CanonEntityDraft]:
    drafts: list[CanonEntityDraft] = []
    current: CanonEntityDraft | None = None
    current_lines: list[str] = []
    last_field: str | None = None

    def finalize() -> None:
        nonlocal current, current_lines, last_field
        if current is not None:
            current.source_excerpt = truncate_text("\n".join(current_lines).strip(), 1200)
            drafts.append(current)
        current = None
        current_lines = []
        last_field = None

    for raw_line in content.splitlines():
        heading = HEADING_RE.match(raw_line)
        bold_name = BOLD_NAME_RE.match(raw_line)
        is_heading = bool(heading)
        is_bold_name = bool(bold_name) and not heading
        if is_heading or is_bold_name:
            finalize()
            header_text = heading.group("header") if heading else bold_name.group("name")  # type: ignore[union-attr]
            current = _start_block(header_text or "")
            current_lines = [raw_line]
            last_field = None
            continue
        if current is None:
            # Tolerate content before the first heading; a bare
            # 'Name: ...' bullet opens an implicit first block.
            implicit = BULLET_FIELD_RE.match(raw_line)
            if implicit and implicit.group("label").strip().lower() == "name":
                current = CanonEntityDraft(entity_type="character", name="")
                current_lines = [raw_line]
                last_field = _apply_field(current, implicit.group("label"), implicit.group("value"))
            continue

        current_lines.append(raw_line)
        bullet = BULLET_FIELD_RE.match(raw_line)
        if bullet:
            last_field = _apply_field(current, bullet.group("label"), bullet.group("value"))
            continue
        stripped = raw_line.strip()
        if stripped and not stripped.startswith(("#", "-")) and last_field:
            # Continuation of the previous multi-line field value.
            fields = current.fields
            fields[last_field] = truncate_text(
                f"{fields[last_field]}\n{stripped}", FIELD_LIMITS.get(last_field, 4000)
            )
    finalize()
    # Bare section headings ("# Character Bible") carry no facts; keep
    # only blocks with at least one content field besides the name.
    return [
        draft
        for draft in drafts
        if draft.fields.get("name") and any(key != "name" for key in draft.fields)
    ]


def _start_block(header_text: str) -> CanonEntityDraft:
    """Interpret a block heading such as 'Character: Mira Vale'."""
    entity_type = "character"
    name = header_text
    warning: str | None = None

    if ":" in header_text:
        prefix, _, rest = header_text.partition(":")
        alias = prefix.strip().lower().lstrip("*").strip()
        if alias in TYPE_ALIASES:
            entity_type = TYPE_ALIASES[alias]
            name = rest.strip() or prefix.strip()
        elif alias in {"scene", "step", "overview"}:
            # Section headers like 'Scene overview' are not entities;
            # keep scanning inside them for 'Name:' bullets.
            name = ""
            warning = None
    name = name.strip().lstrip("*").strip("- ").strip()

    draft = CanonEntityDraft(entity_type=entity_type, name=name)
    if not name:
        draft.warnings.append(
            f"Heading '{header_text}' does not name a canon record; "
            "falling back to 'Name:' bullets inside the block."
        )
    if warning:
        draft.warnings.append(warning)
    if name:
        draft.fields["name"] = name
    return draft


def _apply_field(draft: CanonEntityDraft, label: str, value: str) -> str | None:
    normalized = label.strip().lower()
    field_name = FIELD_LABELS.get(normalized)
    if field_name is None:
        draft.warnings.append(
            f"Unknown field '{label.strip()}' for "
            f"'{draft.fields.get('name', draft.name)}' was preserved only in the Step 7 record."
        )
        return None
    cleaned = value.strip()
    if TBD_RE.match(cleaned):
        draft.warnings.append(
            f"Field '{label.strip()}' for '{draft.fields.get('name', draft.name)}' "
            "is marked TBD; it stays empty in the proposal."
        )
        cleaned = ""
    existing = draft.fields.get(field_name, "")
    merged = f"{existing}\n{cleaned}".strip() if existing and cleaned else (existing or cleaned)
    draft.fields[field_name] = truncate_text(merged, FIELD_LIMITS.get(field_name, 4000))
    return field_name


def _build_create_proposal(
    create: CanonEntityCreate,
    source_ref: str,
    source_excerpt: str,
) -> WritebackProposalCreate:
    title = truncate_text(f"Create canon {create.entity_type}: {create.name}", 160)
    rationale = (
        "Extracted from Snowflake Step 7 artifact. "
        f"Source excerpt: {truncate_text(source_excerpt, 600)}"
    )
    return WritebackProposalCreate(
        target="canon_entity",
        action="create",
        title=title,
        rationale=rationale,
        payload=create.model_dump(),
        source_ref=source_ref,
    )


def _build_update_proposal(
    create: CanonEntityCreate,
    target: CanonEntity,
    source_ref: str,
    source_excerpt: str,
) -> WritebackProposalCreate | None:
    changes: dict[str, dict[str, str]] = {}
    proposed = create.model_dump()
    current = target.model_dump()
    for field_name in ("summary", "current_state", "constraints", "last_seen", "timeline_notes"):
        after = str(proposed.get(field_name, "")).strip()
        before = str(current.get(field_name, "")).strip()
        if after and after != before:
            changes[field_name] = {"before": before, "after": after}
    if not changes:
        return None
    title = truncate_text(f"Update canon {target.entity_type}: {target.name}", 160)
    rationale = (
        "Extracted from Snowflake Step 7 artifact as an update to the existing "
        f"record {target.id} (version {target.version}). "
        f"Source excerpt: {truncate_text(source_excerpt, 600)}"
    )
    return WritebackProposalCreate(
        target="canon_entity",
        action="update",
        title=title,
        rationale=rationale,
        payload={},
        source_ref=source_ref,
        target_record_id=target.id,
        expected_version=target.version,
        changes=changes,
    )
