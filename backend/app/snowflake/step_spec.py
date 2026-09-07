"""Canonical Snowflake Method step specification.

This module is deliberately framework-free. Services, Wiki policy, validators,
and HTTP projections all derive their step metadata from this one definition.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SnowflakeStepSpec:
    number: int
    title: str
    artifact_type: str
    description: str
    dependencies: tuple[int, ...]
    optional: bool = False
    schema_version: int = 1
    validator_name: str = "markdown_projection"
    virtual: bool = False


SNOWFLAKE_STEP_SPECS: tuple[SnowflakeStepSpec, ...] = (
    SnowflakeStepSpec(
        1, "One Sentence", "story_contract", "Distill the novel into a single-sentence promise.", ()
    ),
    SnowflakeStepSpec(
        2,
        "One Paragraph",
        "plot_seed",
        "Expand the promise into setup, three escalating disasters, and an ending.",
        (1,),
        validator_name="one_paragraph",
    ),
    SnowflakeStepSpec(
        3,
        "Character Summary",
        "character_seeds",
        "Define each major character's motivation, goal, conflict, epiphany, and viewpoint summary.",
        (1, 2),
        validator_name="character_summary",
    ),
    SnowflakeStepSpec(
        4,
        "One Page Synopsis",
        "plot_synopsis",
        "Expand and reference every Step 2 story beat in a one-page synopsis.",
        (1, 2, 3),
        validator_name="one_page_synopsis",
    ),
    SnowflakeStepSpec(
        5,
        "Character Viewpoints",
        "character_pov_lines",
        "Expand the story from each major character's knowledge and viewpoint.",
        (3, 4),
        validator_name="character_viewpoints",
    ),
    SnowflakeStepSpec(
        6,
        "Expanded Synopsis",
        "expanded_plot",
        "Expand the causal outline as act, section, and sequence records.",
        (4, 5),
        validator_name="expanded_synopsis",
    ),
    SnowflakeStepSpec(
        7,
        "Character Bible",
        "canon_entities",
        "Build complete character profiles while keeping confirmed Canon facts explicit.",
        (3, 5, 6),
        validator_name="character_bible",
    ),
    SnowflakeStepSpec(
        8,
        "Scene List",
        "scene_contracts",
        "Compile the plan into reviewable scene contracts and story-thread actions.",
        (6, 7),
        validator_name="scene_list",
    ),
    SnowflakeStepSpec(
        9,
        "Scene Expansion",
        "expanded_scenes",
        "Expand scenes into detailed beats, emotional change, and chapter plans.",
        (6, 7, 8),
        optional=True,
        validator_name="scene_expansion",
    ),
    SnowflakeStepSpec(
        10,
        "Draft Manuscript",
        "manuscript",
        "Track scene-based Manuscript proposal and revision coverage.",
        (8, 9),
        validator_name="manuscript_coverage",
        virtual=True,
    ),
)

_BY_NUMBER = {spec.number: spec for spec in SNOWFLAKE_STEP_SPECS}


def get_step_spec(step_number: int) -> SnowflakeStepSpec:
    try:
        return _BY_NUMBER[step_number]
    except KeyError as exc:
        raise ValueError(f"Unsupported Snowflake step: {step_number}") from exc


def validate_step_graph() -> None:
    """Raise when the canonical dependency graph is incomplete or cyclic."""
    expected = set(range(1, 11))
    if set(_BY_NUMBER) != expected:
        raise ValueError(
            "Snowflake step specification must define steps 1 through 10 exactly once."
        )
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(step: int) -> None:
        if step in visiting:
            raise ValueError("Snowflake step dependency graph contains a cycle.")
        if step in visited:
            return
        visiting.add(step)
        for dependency in _BY_NUMBER[step].dependencies:
            if dependency not in _BY_NUMBER:
                raise ValueError(f"Snowflake step {step} has unknown dependency {dependency}.")
            visit(dependency)
        visiting.remove(step)
        visited.add(step)

    for number in sorted(_BY_NUMBER):
        visit(number)


validate_step_graph()
