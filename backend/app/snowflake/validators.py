"""Pure Snowflake contract validation used at provider and acceptance boundaries."""

import json
import re
from typing import Any

from pydantic import ValidationError

from app.models import (
    SnowflakeGeneratedRecord,
    SnowflakeGeneratedRecordSet,
    SnowflakeValidationFinding,
    SnowflakeValidationReport,
)
from app.snowflake.contracts import (
    CharacterBibleRecord,
    RECORD_CONTRACTS,
    RECORD_STEP_NUMBERS,
    STEP_CONTRACTS,
    WorldBibleRecord,
)
from app.analysis.consistency import forbidden_capability_terms


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
    """Validate an artifact revision at its acceptance boundary.

    Steps 6-9 are record-authoritative. Their legacy blob revisions may still be
    viewed or rejected, but cannot become accepted heads.
    """
    if step_number in RECORD_STEP_NUMBERS:
        return SnowflakeValidationReport(
            step_number=step_number,
            status="failed",
            findings=[
                SnowflakeValidationFinding(
                    code="record_authority_required",
                    severity="critical",
                    message=(
                        f"Step {step_number} is committed through validated record revisions; "
                        "a blob Artifact revision cannot become its accepted head."
                    ),
                )
            ],
        )
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
        if not validated.disaster_2.protagonist_choice_or_action or not validated.disaster_3.protagonist_choice_or_action:
            findings.append(
                SnowflakeValidationFinding(
                    code="disaster_protagonist_causality_missing",
                    severity="critical",
                    message="Disasters 2 and 3 must identify the protagonist choice or action that helps cause them.",
                )
            )
    if step_number == 4:
        beat_ids = {paragraph.source_beat for paragraph in validated.paragraphs}
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


def record_contract_for(step_number: int, payload: dict[str, Any]):
    if step_number == 7:
        return (
            WorldBibleRecord
            if payload.get("record_type") in {"world", "location", "item", "faction"}
            else CharacterBibleRecord
        )
    return RECORD_CONTRACTS.get(step_number)


def validate_snowflake_record_payload(
    step_number: int, payload: dict[str, Any]
) -> SnowflakeValidationReport:
    contract = record_contract_for(step_number, payload)
    if contract is None:
        return SnowflakeValidationReport(
            step_number=step_number,
            status="failed",
            findings=[
                SnowflakeValidationFinding(
                    code="record_contract_missing",
                    severity="critical",
                    message=f"Snowflake step {step_number} has no record contract.",
                )
            ],
        )
    try:
        contract.model_validate(payload)
    except ValidationError as exc:
        return SnowflakeValidationReport(
            step_number=step_number,
            status="failed",
            findings=[
                SnowflakeValidationFinding(
                    code="record_contract_validation_error",
                    severity="critical",
                    message=error["msg"],
                    path=".".join(str(part) for part in error["loc"]),
                    evidence=str(error.get("input", ""))[:240],
                )
                for error in exc.errors(include_url=False)
            ],
        )
    return SnowflakeValidationReport(step_number=step_number, status="passed")


def validate_scene_record_set_context(
    records: list,
    canon_entities: list,
    story_threads: list,
) -> SnowflakeValidationReport:
    """Validate Step 8 references and sequence invariants at the accepted-head boundary."""
    canon_ids = {entity.id for entity in canon_entities}
    known_threads = {
        value
        for thread in story_threads
        for value in (thread.id, thread.title.strip().lower())
    }
    seen_positions: set[int] = set()
    findings: list[SnowflakeValidationFinding] = []
    for record in records:
        try:
            payload = RECORD_CONTRACTS[8].model_validate(record.payload)
        except ValidationError as exc:
            findings.extend(
                SnowflakeValidationFinding(
                    code="record_contract_validation_error",
                    severity="critical",
                    message=error["msg"],
                    path=".".join(str(part) for part in error["loc"]),
                    evidence=str(error.get("input", ""))[:240],
                )
                for error in exc.errors(include_url=False)
            )
            continue
        if record.position in seen_positions:
            findings.append(
                SnowflakeValidationFinding(
                    code="duplicate_scene_sequence",
                    severity="critical",
                    message=f"Scene sequence {record.position} is duplicated.",
                    path=f"records.{record.record_id}.position",
                )
            )
        if record.position > 999:
            findings.append(
                SnowflakeValidationFinding(
                    code="scene_sequence_out_of_range",
                    severity="critical",
                    message="Scene sequence must be between 1 and 999.",
                    path=f"records.{record.record_id}.position",
                )
            )
        seen_positions.add(record.position)
        for canon_id in payload.required_canon_refs:
            if canon_id not in canon_ids:
                findings.append(
                    SnowflakeValidationFinding(
                        code="unknown_required_canon",
                        severity="critical",
                        message=f"Required Canon entity '{canon_id}' does not exist.",
                        path=f"records.{record.record_id}.required_canon_refs",
                    )
                )
        for action in payload.story_thread_actions:
            if action.action != "open" and action.thread_id.lower() not in known_threads:
                findings.append(
                    SnowflakeValidationFinding(
                        code="unknown_story_thread",
                        severity="critical",
                        message=(
                            f"StoryThread '{action.thread_id}' must exist before "
                            f"the '{action.action}' action is accepted."
                        ),
                        path=f"records.{record.record_id}.story_thread_actions",
                    )
                )
    return SnowflakeValidationReport(
        step_number=8,
        status="failed" if findings else "passed",
        findings=findings,
    )


def validate_snowflake_record_generation(
    step_number: int,
    content: str,
    expected_record_ids: list[str] | None,
) -> tuple[list[SnowflakeGeneratedRecord], SnowflakeValidationReport]:
    """Validate provider output for a full or targeted Step 6-9 generation.

    ``None`` accepts a newly generated record set. A concrete list requires the
    provider to return exactly those accepted record IDs.
    """
    payload = structured_payload_from_content(content)
    findings: list[SnowflakeValidationFinding] = []
    try:
        generated = SnowflakeGeneratedRecordSet.model_validate(payload)
    except ValidationError as exc:
        generated = SnowflakeGeneratedRecordSet.model_construct(records=[])
        findings.extend(
            SnowflakeValidationFinding(
                code="record_generation_shape_invalid",
                severity="critical",
                message=error["msg"],
                path=".".join(str(part) for part in error["loc"]),
                evidence=str(error.get("input", ""))[:240],
            )
            for error in exc.errors(include_url=False)
        )

    returned_ids = [record.record_id for record in generated.records]
    returned = set(returned_ids)
    if len(returned_ids) != len(returned):
        findings.append(
            SnowflakeValidationFinding(
                code="duplicate_record_id",
                severity="critical",
                message="Targeted generation returned a record more than once.",
            )
        )
    expected = set(expected_record_ids or [])
    if expected_record_ids is not None and returned != expected:
        findings.append(
            SnowflakeValidationFinding(
                code="target_record_mismatch",
                severity="critical",
                message="Targeted generation must return exactly the selected record IDs.",
                evidence=f"expected={sorted(expected)} returned={sorted(returned)}",
            )
        )

    for index, record in enumerate(generated.records):
        report = validate_snowflake_record_payload(step_number, record.payload)
        findings.extend(
            finding.model_copy(
                update={
                    "path": ".".join(
                        part
                        for part in (
                            "records",
                            str(index),
                            "payload",
                            finding.path,
                        )
                        if part
                    )
                }
            )
            for finding in report.findings
        )

    return generated.records, SnowflakeValidationReport(
        step_number=step_number,
        status="failed" if findings else "passed",
        findings=findings,
    )


_CONSISTENCY_EXCLUDED_FIELDS = {
    "confirmed_facts",
    "constraints",
    "does_not_know",
    "forbidden_facts",
    "forbidden_fact_refs",
    "required_canon_ids",
    "required_canon_refs",
}


def _claim_text(value: Any, *, field_name: str = "") -> str:
    """Flatten generated claims while excluding fields that merely quote constraints."""
    if field_name in _CONSISTENCY_EXCLUDED_FIELDS:
        return ""
    if isinstance(value, dict):
        return "\n".join(
            _claim_text(child, field_name=str(key)) for key, child in value.items()
        )
    if isinstance(value, list):
        return "\n".join(_claim_text(child, field_name=field_name) for child in value)
    return str(value) if value is not None else ""


def validate_snowflake_canon_consistency(
    step_number: int,
    content: str,
    canon_entities: list,
) -> SnowflakeValidationReport:
    """Compare generated claims with explicit prohibitions in accepted Canon.

    The rule is intentionally evidence-based: it only reports a finding when
    the generated output names the Canon entity and also states a capability
    that the entity's accepted constraints explicitly forbid.
    """
    payload = structured_payload_from_content(content)
    claims = _claim_text(payload) if payload else content
    claims_lower = claims.lower()
    findings: list[SnowflakeValidationFinding] = []
    for entity in canon_entities:
        name = entity.name.strip()
        if not name or name.lower() not in claims_lower:
            continue
        for term in forbidden_capability_terms(entity.constraints):
            position = claims_lower.find(term.lower())
            if position < 0:
                continue
            start = max(0, position - 80)
            end = min(len(claims), position + len(term) + 80)
            findings.append(
                SnowflakeValidationFinding(
                    code="canon_constraint_conflict",
                    severity="warning",
                    message=(
                        f"Generated claims mention '{term}' for {name}, while accepted Canon "
                        "explicitly forbids that capability."
                    ),
                    path=f"canon.{entity.id}.constraints",
                    evidence=claims[start:end].replace("\n", " "),
                )
            )
    return SnowflakeValidationReport(
        step_number=step_number,
        status="warnings" if findings else "passed",
        findings=findings,
    )
