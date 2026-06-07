from dataclasses import dataclass


@dataclass(frozen=True)
class SnowflakeWikiStagePolicy:
    step: int
    artifact_type: str
    planned_source_steps: tuple[int, ...]
    include_observed: bool
    insight_kinds: tuple[str, ...]


STAGE_POLICIES = {
    1: SnowflakeWikiStagePolicy(
        step=1,
        artifact_type="story_contract",
        planned_source_steps=(),
        include_observed=False,
        insight_kinds=("story_promise_gap", "theme_conflict"),
    ),
    2: SnowflakeWikiStagePolicy(
        step=2,
        artifact_type="plot_seed",
        planned_source_steps=(1,),
        include_observed=False,
        insight_kinds=("causal_gap", "ending_misalignment"),
    ),
    3: SnowflakeWikiStagePolicy(
        step=3,
        artifact_type="character_seeds",
        planned_source_steps=(1, 2),
        include_observed=False,
        insight_kinds=("motivation_gap", "relationship_gap"),
    ),
    4: SnowflakeWikiStagePolicy(
        step=4,
        artifact_type="plot_synopsis",
        planned_source_steps=(1, 2, 3),
        include_observed=False,
        insight_kinds=("promise_drift", "causal_gap"),
    ),
    5: SnowflakeWikiStagePolicy(
        step=5,
        artifact_type="character_pov_lines",
        planned_source_steps=(3, 4),
        include_observed=False,
        insight_kinds=("viewpoint_conflict", "hidden_motivation_gap"),
    ),
    6: SnowflakeWikiStagePolicy(
        step=6,
        artifact_type="expanded_plot",
        planned_source_steps=(4, 5),
        include_observed=False,
        insight_kinds=("rule_conflict", "plot_difficulty_collapse", "focus_gap"),
    ),
    7: SnowflakeWikiStagePolicy(
        step=7,
        artifact_type="canon_entities",
        planned_source_steps=(3, 5, 6),
        include_observed=False,
        insight_kinds=("ability_conflict", "character_detail_conflict"),
    ),
    8: SnowflakeWikiStagePolicy(
        step=8,
        artifact_type="scene_contracts",
        planned_source_steps=(6, 7),
        include_observed=False,
        insight_kinds=("milestone_coverage_gap", "stalled_state", "missing_character"),
    ),
    9: SnowflakeWikiStagePolicy(
        step=9,
        artifact_type="expanded_scenes",
        planned_source_steps=(6, 7, 8),
        include_observed=False,
        insight_kinds=("contract_coverage_gap", "planned_state_conflict", "thread_gap"),
    ),
    10: SnowflakeWikiStagePolicy(
        step=10,
        artifact_type="manuscript",
        planned_source_steps=(8, 9),
        include_observed=True,
        insight_kinds=("plan_drift", "continuity_conflict", "unused_connection"),
    ),
}


def get_stage_policy(step: int) -> SnowflakeWikiStagePolicy:
    try:
        return STAGE_POLICIES[step]
    except KeyError as exc:
        raise ValueError(f"Unsupported Snowflake step: {step}") from exc
