# LLM Wiki CLP Sidecar Contract (P4)

This document defines the application boundary between AI Writing Studio and a local
LLM Wiki CLP bridge. SQLite Narrative Domain remains the only authoritative story state.
The sidecar compiles accepted manuscript text into candidates; it never commits story state.

## Runtime boundary

```text
FastAPI backend
    |
    | HTTP/JSON, loopback only
    v
Local CLP bridge
    |
    v
llm-wiki-compiler
```

The Python backend does not import Node/CLP SDK types and does not embed the compiler
runtime. The bridge is an independent local process implementing the contract below.

Configure the backend with:

- `AI_WRITING_CLP_BASE_URL` — optional loopback base URL, for example
  `http://127.0.0.1:43117`. If unset, CLP extraction uses a disabled no-op compiler so
  the existing local-first workflow remains compatible.
- `AI_WRITING_CLP_TIMEOUT_SECONDS` — request timeout, default `8`.
- `AI_WRITING_CLP_COMPILER_VERSION` — compiler/run version included in identity and
  idempotency input, default `llm-wiki-clp`.

Only `localhost`, `127.0.0.1`, or `::1` are accepted by the adapter.

## Endpoint

`POST /v1/extract-revision`

The request is the JSON serialization of `KnowledgeCompilerRequest` from
`backend/app/integrations/knowledge_compiler.py`.

Required identity fields include:

- `project_id`
- `revision_id`
- `scene_id`
- `scene_sequence`
- `source_ref` (`manuscript_revision:<revision-id>`)
- `revision_version`
- `profile_name`
- `profile_version`
- `compiler_version`

The request also carries the accepted `revision_text`, minimal current extraction context,
and `domain_schema`, which is a projection of the Python Narrative Domain. Manuscript text
is data, not an instruction to the backend.

## Response

The bridge returns one `KnowledgeCompilerResult` JSON object with the same:

- `project_id`
- `revision_id`
- `source_ref`
- `profile_name`
- `profile_version`
- `compiler_version`

and zero or more:

- `entity_candidates`
- `relation_candidates`
- `lifecycle_candidates`

Every candidate must include `confidence`, `source_ref`, and at least one evidence item.
Every evidence item must reference the same accepted revision and include a bounded excerpt.
The backend validates the entire response with `extra=forbid` models before any proposal is
created.

The sidecar must not return or control SQL, filesystem paths, arbitrary backend actions,
proposal review status, acceptance state, or mutation commands.

## Review and authority

The application flow is:

```text
accepted ManuscriptRevision
-> clp_extraction outbox job
-> AnalysisRun (processor=llmwiki_clp)
-> typed candidate validation
-> WritebackProposal(status=pending_review)
-> author accepts
-> application validation
-> SQLite Narrative Domain mutation
```

Before acceptance, relation and lifecycle candidates are only review proposals. They are not
read by NarrativeGraph, NarrativeSnapshot, or Director Analytics.

## Failure and replay semantics

The manuscript acceptance transaction only enqueues the CLP job; it never calls the sidecar.
Connection failure, timeout, non-2xx response, malformed JSON, identity drift, or invalid
candidate data therefore fail only the derived outbox/analysis work. The accepted revision
remains committed and other outbox jobs continue independently.

The AnalysisService input hash includes the accepted revision, profile/compiler versions,
and relevant extraction context. A successful matching analysis run replays its stored
proposal IDs, including a valid zero-candidate result, without calling the sidecar again.
Failed jobs remain retryable through the existing Outbox mechanism.
