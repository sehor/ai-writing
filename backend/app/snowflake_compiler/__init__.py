"""Structured Snowflake compiler (P1-05).

Turns accepted Snowflake record heads into reviewable proposals:

- Step 7 (canon_entities): canon_extractor produces Canon
  create / update write-back proposals for the existing review flow.
- Step 8 (scene_contracts): scene_parser produces structured
  Scene Contract proposals for batch review.

Design constraints from the improvement plan: parse failures never
touch the database, accepted records stay authoritative, every proposal
carries its structured source and validation findings, and recompiling
unchanged input is idempotent.
"""

from app.snowflake_compiler.canon_extractor import (
    extract_canon_proposals,
    extract_canon_record_proposals,
)
from app.snowflake_compiler.errors import ArtifactNotParseableError
from app.snowflake_compiler.scene_parser import parse_scene_artifact, parse_scene_records

CANON_EXTRACT_STEP = 7
SCENE_PARSE_STEP = 8

__all__ = [
    "CANON_EXTRACT_STEP",
    "ArtifactNotParseableError",
    "SCENE_PARSE_STEP",
    "extract_canon_proposals",
    "extract_canon_record_proposals",
    "parse_scene_artifact",
    "parse_scene_records",
]
