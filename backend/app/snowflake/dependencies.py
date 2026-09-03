"""Pure dependency calculations for Snowflake revision snapshots and staleness."""

from collections.abc import Mapping

from app.snowflake.step_spec import SNOWFLAKE_STEP_SPECS, get_step_spec


def downstream_steps(step_number: int) -> tuple[int, ...]:
    """Return every transitive consumer of ``step_number`` in step order."""
    get_step_spec(step_number)
    affected: set[int] = set()
    frontier = [step_number]
    while frontier:
        current = frontier.pop()
        for spec in SNOWFLAKE_STEP_SPECS:
            if current in spec.dependencies and spec.number not in affected:
                affected.add(spec.number)
                frontier.append(spec.number)
    return tuple(sorted(affected))


def upstream_snapshot(
    step_number: int,
    accepted_heads: Mapping[int, str],
) -> dict[str, str]:
    """Capture the accepted revision IDs directly consumed by a new revision."""
    spec = get_step_spec(step_number)
    return {
        str(dependency): accepted_heads[dependency]
        for dependency in spec.dependencies
        if accepted_heads.get(dependency)
    }
