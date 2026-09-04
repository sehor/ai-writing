# Prompt Management

## Scope

AI Writing Studio manages production Prompt text as versioned, file-backed assets. The first implementation is backend-only: there is no Prompt editing UI, database table, or remote Prompt service.

The runtime boundary is `PromptManager` in `backend/app/prompts/manager.py`. It loads `backend/app/prompts/assets/catalog.toml`, resolves an asset by stable ID and version, and renders variables with strict substitution. Missing assets, unsupported versions, malformed catalogs, and missing variables fail explicitly.

## Ownership

- `app.prompts.manager`: loading, version lookup, reload, and strict rendering.
- `app.prompts.assets`: all production natural-language Prompt templates.
- `app.prompts.registry`: callable Prompt identities and response contracts.
- `app.prompts.snowflake` / `app.prompts.creative`: typed context preparation and `PromptPlan` composition.
- `app.snowflake.contracts`: Pydantic response schemas and version-1 compatibility adapters.
- `app.snowflake.validators`: deterministic acceptance checks.
- `app.llm`: Provider-neutral execution; it must not contain domain Prompt text.

Prompt text belongs in the catalog. Response schemas, authorization, persistence, and business validation do not.

## Editing a Prompt

1. Edit the matching asset in `backend/app/prompts/assets/catalog.toml`.
2. Bump the asset version when observable instructions or output semantics change.
3. If a response shape changes, update the Pydantic contract and schema version separately.
4. Update the Prompt snapshot hash.
5. Restart the backend so the default manager and registry reload the catalog.
6. Run the Prompt Manager, Prompt registry, Snowflake validator, workflow, and integration tests.

The ten `snowflake.stepNN.method` assets are authoritative runtime configuration. `tests/test_prompt_manager.py` verifies that the complete Step 1-10 asset set exists, is versioned, and renders successfully. Planning and design documents may describe intended changes, but runtime code and tests do not read them as configuration.

## Runtime Composition

Snowflake generation composes three messages:

1. the shared system asset;
2. a rendered project/upstream/Canon/Memory context asset;
3. the exact documented step method plus the runtime request and response contract.

The runtime additions provide current project data, author direction, selected record IDs, batching envelopes, and the executable JSON Schema. They may specialize serialization but must not weaken or contradict the documented method rules.

## Compatibility

Snowflake response contracts are version 2. Version-1 payload adapters run only at the validation boundary so existing projects remain readable. New generated output and advertised JSON Schema use the version-2 field names from the ten-step specification.

Step 10 now advertises the structured scene-draft response contract. The manuscript workflow extracts `manuscript_prose` for the review proposal and surfaces counts for fact candidates, design deviations, and continuity questions. Plain Markdown remains accepted only as a compatibility path for older gateways.
