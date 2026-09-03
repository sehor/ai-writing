from dataclasses import dataclass

from app.snowflake.step_spec import SNOWFLAKE_STEP_SPECS


@dataclass(frozen=True)
class SnowflakeWikiStagePolicy:
    step: int
    artifact_type: str
    planned_source_steps: tuple[int, ...]
    include_observed: bool
    insight_kinds: tuple[str, ...]


_INSIGHT_KINDS = {
    1: ("story_promise_gap", "theme_conflict"),
    2: ("causal_gap", "ending_misalignment"),
    3: ("motivation_gap", "relationship_gap"),
    4: ("promise_drift", "causal_gap"),
    5: ("viewpoint_conflict", "hidden_motivation_gap"),
    6: ("rule_conflict", "plot_difficulty_collapse", "focus_gap"),
    7: ("ability_conflict", "character_detail_conflict"),
    8: ("milestone_coverage_gap", "stalled_state", "missing_character"),
    9: ("contract_coverage_gap", "planned_state_conflict", "thread_gap"),
    10: ("plan_drift", "continuity_conflict", "unused_connection"),
}

STAGE_POLICIES = {
    spec.number: SnowflakeWikiStagePolicy(
        step=spec.number,
        artifact_type=spec.artifact_type,
        planned_source_steps=spec.dependencies,
        include_observed=spec.virtual,
        insight_kinds=_INSIGHT_KINDS[spec.number],
    )
    for spec in SNOWFLAKE_STEP_SPECS
}


def get_stage_policy(step: int) -> SnowflakeWikiStagePolicy:
    try:
        return STAGE_POLICIES[step]
    except KeyError as exc:
        raise ValueError(f"Unsupported Snowflake step: {step}") from exc
