# Spec: Local LLM Wiki Lightweight Compiler

## Objective

Upgrade the built-in `LocalFileLlmWiki` so it behaves more like a small local knowledge compiler while keeping the existing `LlmWiki` port stable. The user is the author working in AI Writing Studio; success means staged Snowflake and manuscript evidence is easier to inspect, ranked more usefully, and reports deterministic gaps without depending on the external TypeScript `llm-wiki-compiler`.

## Tech Stack

- Python 3.11+ with FastAPI and Pydantic.
- SQLite remains owned by the app data layer.
- Local LLM Wiki persistence remains under `backend/data/projects/{project_id}/modules/llm_wiki/`.
- No new runtime dependency for this slice.

## Commands

- Focused tests: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_llm_wiki_interface -v`
- Integration tests: `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_llm_wiki_integration -v`
- Compile check: `python -m compileall backend\app`
- Frontend build is not required for backend-only LLM Wiki slices.

## Project Structure

- `backend/app/llm_wiki/interfaces.py`: stable public port and DTOs.
- `backend/app/llm_wiki/local_backend.py`: local lightweight implementation.
- `backend/app/llm_wiki/stage_protocol.py`: Snowflake visibility rules.
- `backend/tests/test_llm_wiki_interface.py`: local backend contract tests.
- `docs/superpowers/specs/`: living specs for larger changes.

## Code Style

Keep helpers local until reuse is real:

```python
def score_document(document: WikiSourceDocument, query: WikiContextQuery) -> int:
    tokens = tokenize(query.instruction)
    if not tokens:
        return 0
    haystack = f"{document.title}\n{document.content}".lower()
    return sum(3 if token in document.title.lower() else 1 for token in tokens if token in haystack)
```

Use plain functions and standard library parsing. Do not add adapter layers until a second implementation needs them.

## Testing Strategy

Use `unittest` and temporary directories. Tests should assert behavior, not implementation calls:

- ingest writes existing JSON plus a readable markdown mirror;
- ingest rebuilds a deterministic `wiki/concepts/` projection from active approved JSON sources;
- ingest rebuilds `wiki/index.md` from active approved projected pages;
- context retrieval still obeys stage, scope, and story-position boundaries;
- instruction matches rank higher than unrelated visible sources;
- missing visible evidence creates an advisory gap insight.

## Boundaries

- Always: preserve `LlmWiki` DTO compatibility, stage visibility, planned/observed separation, and supersession behavior.
- Ask first: adding dependencies, changing API response models, replacing the storage layout, or invoking external Node tools from requests.
- Never: pass app snapshots, Canon records, Memory records, provider config, or data-store objects into the LLM Wiki port.

## Success Criteria

- Existing LLM Wiki tests still pass.
- Local source documents have a human-readable markdown mirror.
- Active approved source documents have deterministic concept projection pages.
- `wiki/index.md` lists active projected concept pages and excludes superseded sources.
- Retrieval is deterministic and ranks instruction-relevant evidence before merely visible evidence.
- `analyze` returns a deterministic advisory gap when no evidence is visible.
- No external `llm-wiki-compiler` code is copied into this project.

## Open Questions

- Whether external `llm-wiki-compiler` integration should be a subprocess adapter or a Node bridge.
