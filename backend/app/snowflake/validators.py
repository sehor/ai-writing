"""Pure Snowflake contract validation used at provider and acceptance boundaries."""

import json
import re
from typing import Any

from pydantic import ValidationError

from app.models import SnowflakeValidationFinding, SnowflakeValidationReport
from app.snowflake.contracts import STEP_CONTRACTS


_JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def structured_payload_from_content(content: str) -> dict[str, Any]:
    candidate = content.strip()
    match = _JSON_FENCE.match(candidate)
    if match:
        candidate = match.group(1).strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        if start < 0:
            return {}
        candidate = candidate[start:]
    try:
        parsed, _end = json.JSONDecoder().raw_decode(candidate)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def validate_snowflake_payload(
    step_number: int,
    content: str,
    payload: dict[str, Any] | None = None,
) -> SnowflakeValidationReport:
    """Validate structured steps; report honestly when a step has no strict v1 schema yet."""
    contract = STEP_CONTRACTS.get(step_number)
    candidate = payload or structured_payload_from_content(content)
    if contract is None:
        return SnowflakeValidationReport(
            step_number=step_number,
            status="skipped",
            findings=[
                SnowflakeValidationFinding(
                    code="schema_not_run",
                    severity="warning",
                    message="This step is validated by its record compiler or Manuscript workflow.",
                )
            ],
        )
    if not candidate:
        if step_number == 1 and len([line for line in content.splitlines() if line.strip()]) == 1:
            return SnowflakeValidationReport(
                step_number=step_number,
                status="warnings",
                findings=[
                    SnowflakeValidationFinding(
                        code="structured_payload_missing",
                        severity="warning",
                        message="One-sentence prose is present, but its structured fields were not supplied.",
                    )
                ],
            )
        return SnowflakeValidationReport(
            step_number=step_number,
            status="failed",
            findings=[
                SnowflakeValidationFinding(
                    code="structured_payload_missing",
                    severity="critical",
                    message=f"Step {step_number} requires a versioned structured JSON payload.",
                )
            ],
        )
    try:
        validated = contract.model_validate(candidate)
    except ValidationError as exc:
        findings = [
            SnowflakeValidationFinding(
                code="contract_validation_error",
                severity="critical",
                message=error["msg"],
                path=".".join(str(part) for part in error["loc"]),
                evidence=str(error.get("input", ""))[:240],
            )
            for error in exc.errors(include_url=False)
        ]
        return SnowflakeValidationReport(
            step_number=step_number,
            status="failed",
            findings=findings,
        )

    findings: list[SnowflakeValidationFinding] = []
    if step_number == 2:
        beats = validated.model_dump()
        if not beats["disaster_2"]["escalation"] or not beats["disaster_3"]["escalation"]:
            findings.append(
                SnowflakeValidationFinding(
                    code="disaster_escalation_missing",
                    severity="critical",
                    message="Disasters 2 and 3 must explain how they escalate the prior disaster.",
                )
            )
    if step_number == 4:
        beat_ids = {paragraph.beat_id for paragraph in validated.paragraphs}
        missing = {"setup", "disaster_1", "disaster_2", "disaster_3", "ending"} - beat_ids
        if missing:
            findings.append(
                SnowflakeValidationFinding(
                    code="beat_coverage_missing",
                    severity="critical",
                    message="Synopsis does not cover every Step 2 beat: " + ", ".join(sorted(missing)),
                )
            )
    return SnowflakeValidationReport(
        step_number=step_number,
        status="failed" if any(f.severity == "critical" for f in findings) else "passed",
        findings=findings,
    )
