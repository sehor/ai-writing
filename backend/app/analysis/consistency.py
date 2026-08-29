"""Deterministic consistency checker (P1-06).

Compares one accepted manuscript revision against its Scene Contract and
the project's Canon records using local text rules only. Every finding
carries the matched prose excerpt as evidence so a human can verify it;
nothing here mutates project state. Rules that need semantic judgement
(POV embodiment, goal/conflict/turning-point presence, cross-revision
state conflicts) are intentionally left to provider-backed processors.
"""

import re
from hashlib import sha1

from app.analysis.models import ConsistencyFinding

CONSISTENCY_PROCESSOR = "consistency_checker"

RULE_FORBIDDEN_FACT_MENTION = "FORBIDDEN_FACT_MENTION"
RULE_CONSTRAINT_CAPABILITY_USED = "CONSTRAINT_CAPABILITY_USED"
RULE_REQUIRED_CANON_MISSING = "REQUIRED_CANON_MISSING"
RULE_POV_NAME_ABSENT = "POV_NAME_ABSENT"
RULE_READER_KNOWLEDGE_LEAK = "READER_KNOWLEDGE_LEAK"

# Terms shorter than this are too noisy to match verbatim in prose.
MIN_TERM_LENGTH = 4
EXCERPT_CONTEXT = 60

# Constraint sentences that forbid a capability, e.g.
# "禁止飞行", "不能使用魔法", "must not leave the city".
_FORBIDDEN_PATTERNS = [
    "(?:禁止|不得|不能|不可|无法|切勿)([^，。；！？,;.!?!\\n]{2,24})",
    "(?:must not|cannot|never|is forbidden to|forbidden to)\\s+([^，。；,;.!?!\\n]{2,40})",
]


def build_consistency_fingerprint(revision, scene, canon_entities, story_facts=()) -> dict:
    """Deterministic description of every input the checker reads."""
    return {
        "content": revision.content,
        "version": revision.version,
        "scene": (
            {
                "pov": scene.pov,
                "goal": scene.goal,
                "conflict": scene.conflict,
                "turning_point": scene.turning_point,
                "required_canon": scene.required_canon,
                "forbidden_facts": scene.forbidden_facts,
            }
            if scene is not None
            else None
        ),
        "canon": sorted(
            f"{entity.id}:{entity.name}:v{entity.version}:{entity.constraints}"
            for entity in canon_entities
        ),
        "story_facts": sorted(
            f"{fact.id}:{fact.subject}:{fact.predicate}:{fact.value}:"
            f"{fact.valid_from_scene}:{fact.valid_to_scene}:{fact.reader_visible_from}:{fact.status}"
            for fact in story_facts
        ),
    }


def _excerpt(content: str, position: int, term_length: int) -> str:
    start = max(0, position - EXCERPT_CONTEXT)
    end = min(len(content), position + term_length + EXCERPT_CONTEXT)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return prefix + content[start:end].replace("\n", " ") + suffix


def _head_excerpt(content: str) -> str:
    flat = content[: EXCERPT_CONTEXT * 2].replace("\n", " ")
    return flat + ("…" if len(content) > EXCERPT_CONTEXT * 2 else "")


def _finding_id(rule_code: str, source_ref: str, detail: str) -> str:
    digest = sha1(f"{rule_code}|{source_ref}|{detail}".encode("utf-8")).hexdigest()[:10]
    return f"{rule_code.lower()}-{digest}"


def split_contract_terms(value: str) -> list[str]:
    """Split free-text contract fields into comparable terms."""
    terms = []
    seen = set()
    for raw in value.replace(";", "\n").replace(",", "\n").splitlines():
        term = raw.strip(" -\t·")
        lowered = term.lower()
        if len(term) >= MIN_TERM_LENGTH and lowered not in seen:
            seen.add(lowered)
            terms.append(term)
    return terms


_CAPABILITY_LEAD_WORDS = (
    # Common verbs between the prohibition and the capability itself,
    # e.g. "不能使用魔法" forbids 魔法, not the literal string "使用魔法".
    "使用",
    "施展",
    "掌握",
    "拥有",
    "进行",
    "习得",
    "修炼",
    "携带",
    "use ",
    "using ",
    "cast ",
    "casting ",
    "carry ",
    "wield ",
)


def _capability_variants(term: str) -> list[str]:
    """The captured phrase plus the phrase without a leading verb."""
    variants = [term]
    lowered = term.lower()
    for lead in _CAPABILITY_LEAD_WORDS:
        if lowered.startswith(lead):
            rest = term[len(lead) :].lstrip(" :：")
            if len(rest) >= 2:
                variants.append(rest)
    return variants


def forbidden_capability_terms(constraints: str) -> list[str]:
    """Extract capability phrases that a Canon record explicitly forbids."""
    terms: list[str] = []
    seen = set()
    for pattern in _FORBIDDEN_PATTERNS:
        for match in re.finditer(pattern, constraints, flags=re.IGNORECASE):
            term = match.group(1).strip(" \"'“”‘’、")
            if len(term) < 2:
                continue
            # Trim trailing connective words that belong to the sentence,
            # not the capability itself.
            term = re.sub(r"(?:的|者|的人)$", "", term).strip()
            for variant in _capability_variants(term):
                lowered = variant.lower()
                if len(variant) >= 2 and lowered not in seen:
                    seen.add(lowered)
                    terms.append(variant)
    return terms


def check_revision(revision, scene, canon_entities, story_facts=()) -> list[ConsistencyFinding]:
    """Run every deterministic rule over one revision.

    ``revision`` is a ManuscriptRevision; ``scene`` may be ``None`` when the
    scene contract no longer exists; ``canon_entities`` are the project's
    Canon records at their current versions.
    """
    findings: list[ConsistencyFinding] = []
    source_ref = f"manuscript_revision:{revision.id}"
    content = revision.content
    content_lower = content.lower()

    # Plan rule 1: a Scene Contract forbidden fact appears verbatim in prose.
    if scene is not None:
        for term in split_contract_terms(scene.forbidden_facts):
            position = content_lower.find(term.lower())
            if position >= 0:
                findings.append(
                    ConsistencyFinding(
                        id=_finding_id(RULE_FORBIDDEN_FACT_MENTION, source_ref, term),
                        severity="critical",
                        rule_code=RULE_FORBIDDEN_FACT_MENTION,
                        title=f"Forbidden fact appears in prose: {term}",
                        description=(
                            "The Scene Contract forbids this fact for the scene, but "
                            "the manuscript states it verbatim."
                        ),
                        manuscript_source_ref=source_ref,
                        manuscript_excerpt=_excerpt(content, position, len(term)),
                        canon_entity_id=None,
                        canon_field="forbidden_facts",
                        expected_value=f"Not present: {term}",
                        observed_value=term,
                        suggested_action=(
                            "Rewrite the passage or relax the Scene Contract, then "
                            "re-run the check before acting on it."
                        ),
                        confidence="exact",
                    )
                )

    # Narrative OS P1: a world fact can already be true while still hidden
    # from the reader. A verbatim value appearing before reader_visible_from
    # is explainable evidence of a possible reveal leak.
    if scene is not None:
        for fact in story_facts:
            if fact.status != "confirmed":
                continue
            if fact.valid_from_scene > scene.sequence:
                continue
            if fact.valid_to_scene is not None and fact.valid_to_scene < scene.sequence:
                continue
            if fact.reader_visible_from is not None and fact.reader_visible_from <= scene.sequence:
                continue
            term = fact.value.strip()
            if len(term) < MIN_TERM_LENGTH:
                continue
            position = content_lower.find(term.lower())
            if position < 0:
                continue
            findings.append(
                ConsistencyFinding(
                    id=_finding_id(RULE_READER_KNOWLEDGE_LEAK, source_ref, fact.id),
                    severity="critical",
                    rule_code=RULE_READER_KNOWLEDGE_LEAK,
                    title=f"Hidden story fact appears in prose: {fact.subject}",
                    description=(
                        "This fact is valid in world state at the scene, but its reader "
                        "visibility boundary has not been reached."
                    ),
                    manuscript_source_ref=source_ref,
                    manuscript_excerpt=_excerpt(content, position, len(term)),
                    canon_entity_id=None,
                    canon_field="reader_visible_from",
                    expected_value=(
                        f"Keep hidden until scene {fact.reader_visible_from}"
                        if fact.reader_visible_from is not None
                        else "Keep hidden from the reader"
                    ),
                    observed_value=term,
                    suggested_action=(
                        "Remove or obscure the reveal, or explicitly move the fact's reader "
                        "visibility boundary earlier after author review."
                    ),
                    confidence="exact",
                )
            )

    # Plan rule 3: Canon declares a forbidden capability and the prose uses
    # that phrase.
    for entity in canon_entities:
        if not entity.constraints:
            continue
        for term in forbidden_capability_terms(entity.constraints):
            position = content_lower.find(term.lower())
            if position < 0:
                continue
            findings.append(
                ConsistencyFinding(
                    id=_finding_id(
                        RULE_CONSTRAINT_CAPABILITY_USED, source_ref, f"{entity.id}:{term}"
                    ),
                    severity="warning",
                    rule_code=RULE_CONSTRAINT_CAPABILITY_USED,
                    title=f"Forbidden capability mentioned: {term}",
                    description=(
                        f"Canon {entity.name} forbids '{term}' in constraints, and the "
                        "prose contains that phrase. Verify whether the prose actually "
                        "depicts the forbidden capability or merely negates it."
                    ),
                    manuscript_source_ref=source_ref,
                    manuscript_excerpt=_excerpt(content, position, len(term)),
                    canon_entity_id=entity.id,
                    canon_field="constraints",
                    expected_value=f"{entity.name}: must not involve {term}",
                    observed_value=term,
                    suggested_action=(
                        "Confirm intent with the author: adjust the prose or update "
                        "the Canon constraint through an accepted write-back."
                    ),
                    confidence="heuristic",
                )
            )

    # Plan rule 5: required Canon is completely missing from prose.
    if scene is not None and scene.required_canon:
        for entity in canon_entities:
            if entity.name.lower() not in scene.required_canon.lower():
                continue
            if entity.name.lower() in content_lower:
                continue
            findings.append(
                ConsistencyFinding(
                    id=_finding_id(RULE_REQUIRED_CANON_MISSING, source_ref, entity.id),
                    severity="warning",
                    rule_code=RULE_REQUIRED_CANON_MISSING,
                    title=f"Required Canon never appears: {entity.name}",
                    description=(
                        f"The Scene Contract requires {entity.name}, but neither the name "
                        "nor any reference appears anywhere in the revision."
                    ),
                    manuscript_source_ref=source_ref,
                    manuscript_excerpt=_head_excerpt(content),
                    canon_entity_id=entity.id,
                    canon_field="required_canon",
                    expected_value=f"Prose mentions {entity.name}",
                    observed_value="No mention found",
                    suggested_action=(
                        "Add the required element, or remove it from the Scene "
                        "Contract if the omission is intentional."
                    ),
                    confidence="exact",
                )
            )

    # Plan rule 2 (heuristic slice): the POV name never appears while the
    # prose does name other Canon entities.
    pov = scene.pov.strip() if scene is not None else ""
    if pov:
        other_named = [
            entity.name
            for entity in canon_entities
            if entity.name.lower() != pov.lower() and entity.name.lower() in content_lower
        ]
        pov_tokens = [token for token in pov.split() if len(token) >= 2]
        pov_present = pov.lower() in content_lower or any(
            token.lower() in content_lower for token in pov_tokens
        )
        if not pov_present:
            findings.append(
                ConsistencyFinding(
                    id=_finding_id(RULE_POV_NAME_ABSENT, source_ref, pov),
                    severity="info",
                    rule_code=RULE_POV_NAME_ABSENT,
                    title=f"POV name absent from prose: {pov}",
                    description=(
                        f"The Scene Contract sets POV to {pov}, but the revision never "
                        "mentions that name"
                        + (
                            f" although it names: {', '.join(other_named[:5])}."
                            if other_named
                            else "."
                        )
                    ),
                    manuscript_source_ref=source_ref,
                    manuscript_excerpt=_head_excerpt(content),
                    canon_entity_id=None,
                    canon_field="pov",
                    expected_value=f"POV {pov} recognisable in prose",
                    observed_value="POV name not found",
                    suggested_action=(
                        "Check whether the viewpoint still reads clearly; naming the "
                        "POV once early in the scene usually suffices."
                    ),
                    confidence="heuristic",
                )
            )

    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: (order[item.severity], item.rule_code, item.id))
    return findings
