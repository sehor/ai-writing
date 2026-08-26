# AI Writing Studio Development Plan

## Current Goal

Build a local-first long-form writing studio around the Snowflake Method. The backend should expose stable business APIs first, while AI generation remains behind project-owned interfaces so the implementation can later use direct model SDKs, LangGraph, or another workflow runtime without changing the API contract.

Canon DB v0, Memory / Style v0, structured Scene Contracts, Chapter Compiler v0, Graph / Structure v0, project-scoped cognition modules, deterministic local workflow, DeepSeek-backed Snowflake runtime, provider-backed manuscript proposals, Manuscript Proposal review v0, accepted manuscript scene state, chapter-level manuscript organization, direct scene editing, manuscript revision history, Markdown export, Canon / Memory write-back proposals, deterministic revision-based write-back suggestions, provider-backed write-back suggestions, structured References / Copilot UI, frontend review tools, frontend contract tests, browser smoke tests, backend route tests, backend edit-versioning tests, CI gates, LLM Wiki outbox, the unified review state machine with Canon-update write-backs, pre-persist proposal validation, idempotent analysis runs, the deterministic consistency report with evidence-backed findings, the structured Snowflake compiler, automatic post-acceptance analysis, focused data repositories coordinated by an explicit unit of work, domain-split frontend stores behind a slim workspace shell, and a real-browser E2E suite against a live backend now exist.

Done in P1-05: Snowflake Step 7 artifacts compile into reviewable Canon create / update write-back proposals through a deterministic local extractor, and Step 8 artifacts parse into persisted Scene Contract proposals (sequence, chapter hint, POV, goal, conflict, turning point, required canon ids, forbidden facts, open threads) that carry their source excerpt and parse warnings.

Done in P1-07: accepting a manuscript proposal now enqueues a consistency-analysis job and a deterministic write-back-analysis job inside the same SQLite transaction as the Wiki outbox job; dispatch happens right after commit, so evidence-backed reports and pending write-back suggestions appear without any manual trigger. Analysis is automatic - accepting its suggestions stays a human decision - failures land on retryable outbox jobs without endangering accepted core data, and provider-backed semantic rules can join later behind the same processor interface.

Done in P2-01 / P2-02: every router is now a pure HTTP layer over application services (`app.services.snowflake_service`, `reference_service`, `writeback_service`), and the provider registry (`app.integrations.provider_registry`) resolves generation backends behind one `WritingProvider` interface — the deterministic local runtime and DeepSeek register by name, Hermes stays an isolated external-agent port under `app.integrations.hermes`, and adding a provider means implementing the protocol, registering it, and flipping configuration.

Done in P2-03: `WritingDataStore` is split into ten focused repositories under `app.data.repositories` over one shared schema module; an explicit `SqliteUnitOfWork` owns the single SQLite connection and the transaction boundary (commit on clean exit, rollback on exception), and cross-aggregate flows — manuscript proposal acceptance with its three outbox jobs, revision restore / edit, scene-proposal batch acceptance, and Canon-update apply — run as `app.data.flows` functions inside exactly one unit of work. The store remains a thin facade with unchanged public signatures, so routers, services, agents, and tests needed no edits. All data roots (SQLite database, LLM Wiki project files, cognition modules) resolve through `app.config.resolve_data_root`, honoring `AI_WRITING_DATA_ROOT` for throwaway E2E environments.

Done in P2-04: the ~2,900-line frontend workspace store is broken into domain stores (`stores/projects|snowflake|canon|memory|manuscript|reviews|graph.ts`) behind a typed `/api` client (`api/client.ts`, `api/errors.ts`) with shared draft-safety services; `workspace.ts` (~360 lines) keeps only project / section / step selection, global runtime status, project-switch orchestration, and genuine cross-store coordination. Twelve components consume domain stores directly while their templates stayed byte-identical, and contract tests assert the same guarantees against the new file locations.

Done in P1-08: a real-browser E2E suite (`e2e/`, Playwright Chromium + Vite JS API + real uvicorn) drives the actual FastAPI backend over a throwaway SQLite root with zero route mocking. The happy path covers UI project creation, Step 7 compile into Canon proposals and their browser acceptance, chapter / scene / proposal flows through acceptance, polling automatic analysis jobs to success, seeding and browser-accepting a Canon update write-back (Canon v2 verified), Markdown export, and a backend restart on the same data root proving full persistence. The failure path blocks wiki ingestion before boot and proves core writes survive index failures, failed jobs surface in the Post-Acceptance panel, and UI retry recovers without duplicate versions.

Done after P1-08 (quick-fix pack): selecting a Canon list entry now fills the editor form with the entity baseline before restoring any cached draft (`stores/canon.ts`); the Post-Acceptance Analysis panel lists all three outbox job types — including `llm_wiki_ingest` as "Wiki index" — with the same Retry action, and both E2E suites exercise it from the UI; the page-close draft guard actually installs now (its `onMounted` never fired inside store setup). The suites run cross-platform (`AI_WRITING_E2E_PYTHON` or venv autodetection) and are wired into CI as an allow-failure `browser-e2e` job pending flake-free runs.

Done in P2-06: schema changes are versioned database migrations (`app.data.migrations`). A `schema_migrations` table records applied `(version, name, applied_at)` rows; startup reads it and applies each pending migration in order inside exactly one transaction together with its bookkeeping row — a failure rolls that migration back completely and stops startup with a `RuntimeError` naming the failed version. Version 1 is the full DDL baseline; versions 2–4 mirror the former additive-column migrations; all migrations stay idempotent so databases from any earlier era converge to the same shape without losing data. Covered by five dedicated tests: empty upgrade, legacy upgrade with row preservation, repeated execution no-op, mid-migration rollback, and single demo seed.

Done in P2-05: the two LLM Wiki paths are merged into one. The Obsidian-compatible Markdown exporter now lives in `app.exports.wiki` (moved verbatim from `app.cognition.llm_wiki`); the never-registered `LocalLlmWikiModule` cognition wrapper around it was dead code at HEAD and is deleted along with the `app.wiki_export` shim, whose test imports `app.exports.wiki` directly. All runtime ingestion / retrieval goes through `app.llm_wiki.interfaces` + `LocalFileLlmWiki`, so README's single architecture description now matches reality.

The next implementation focus is broadening E2E coverage to more Snowflake steps and provider-backed paths, then continuing with P2-05 (merge the two LLM Wiki paths), P2-06 (versioned database migrations), P2-07 (project backup / restore), and P2-08 (runtime observability).

## Near-Term Milestones

1. Project shell
   - Keep project creation and project listing working from the frontend.
   - Keep generated and local environment files out of Git.

2. Workflow boundary
   - Model AI writing as a workflow, not a single agent call.
   - Represent pre-generation, generation, and post-generation agents as explicit steps.
   - Keep the default implementation interface-only until a real AI runtime is selected.

3. Snowflake artifacts
   - Add CRUD APIs for step artifacts.
   - Store artifacts per project and step.
   - Keep the frontend focused on one active project and one active Snowflake step.

4. Local persistence
   - Replace in-memory project state with a simple local database.
   - Keep repository, service, and API layers small.

5. Canon DB foundation
   - Done in v0: typed Canon entities for characters, locations, items, factions, and rules.
   - Done in v0: current state, constraints, last seen, and timeline notes.
   - Done in v0: CRUD APIs and a basic frontend panel.

6. Scene contracts
   - Done in v0: turn Step 8 output into structured records.
   - Done in v0: track POV, goal, conflict, turning point, required Canon, forbidden facts, and open threads.
   - Done in v0: keep raw Snowflake artifact text available as source material.

7. Chapter compiler v0
   - Done in v0: assemble one scene contract plus related Canon into a context package.
   - Done in v0: return a deterministic draft placeholder and checklist before real AI calls.
   - Next: make write-back proposals explicit and reviewable.

8. AI runtime implementation
   - Done in v0: add one deterministic local `WritingWorkflow` implementation.
   - Done in v0: add tracing for each agent step before exposing output in the UI.
   - Next: start with direct SDK calls or LangGraph only after memory/style and review contracts are stable.

9. Memory / Style v0
   - Done in v0: add prose samples, chapter summaries, character voice notes, and style rules.
   - Done in v0: keep these separate from Canon facts.
   - Done in v0: load them into Snowflake workflow and Chapter Compiler context packages.

10. Graph / Structure v0
   - Done in v0: derive lightweight relationship/thread records from Canon and Scene Contracts.
   - Done in v0: report unresolved threads and isolated entities.
   - Done in v0: keep graph output advisory until the author commits changes.
   - Done in v0: move structure analysis behind the `infra_graph` cognition module boundary.

11. Knowledge and cognition module boundaries
   - Done in v0: add `backend/app/cognition/` interfaces for `ContextPacket`, `CommittedContentEvent`, `ModuleReport`, and project snapshots.
   - Done: separate LLM Wiki from project snapshots behind `backend/app/llm_wiki/interfaces.py`.
   - Done: tag ingested sources by Snowflake step, artifact type, `planned` / `observed`, version, scope, and story position.
   - Done: provide stage-aware context retrieval and evidence-backed advisory insight interfaces.
   - Done: keep the local file adapter replaceable through FastAPI dependency injection.
   - Done in v0: isolate style sample ingestion in a project-scoped `memplace` module.
   - Done: route Snowflake generation, scene compilation, and manuscript revision ingestion through the LLM Wiki interface rather than the local adapter.
   - Next: add an external Agent adapter without changing core app routes or workflow signatures.

12. Provider-backed Snowflake workflow runtime
   - Done in v0: call DeepSeek through the app-owned `WritingWorkflow` interface when configured.
   - Done in v0: preserve deterministic local fallback when no provider key exists.
   - Done in v0: expose runtime status in the API and frontend.

13. Manuscript / Version Review v0
   - Done in v0: persist manuscript draft proposals separately from accepted manuscript state.
   - Done in v0: create proposals from deterministic Scene Compiler output.
   - Done in v0: add accept/reject workflow before generated output can mutate committed writing state.
   - Done in v0: write accepted proposals into current manuscript scene draft records with version numbers.
   - Done in v0: preserve manuscript revision history for each accepted version.
   - Done in v0: make Canon and Memory create proposals explicit and reviewable through backend APIs.
   - Done in v0: generate deterministic Canon and Memory write-back suggestions from manuscript revisions.
   - Done in v0: generate provider-backed Canon and Memory suggestions from manuscript revision context.
   - Done in v0: add backend manuscript diff and restore APIs for accepted revisions.
   - Done in v0: add frontend review UI for write-back proposals.
   - Done in v0: expose manuscript diff and restore controls in the frontend.
   - Done in v0: create provider-backed manuscript proposals from Scene Contracts.
   - Done in v0: export accepted manuscript scenes as Markdown.
   - Done in v0: edit accepted manuscript scene drafts directly while preserving revision history.
   - Done in v0: add backend unit tests for manuscript edit versioning.
   - Done in v0: add chapter-level manuscript organization for Scene Contracts and exports.
   - Done in v0: add structured References / Copilot UI for reviewable suggestions.
   - Done in v0: add zero-dependency frontend contract test coverage for References UI wiring.
   - Done in v0: add backend route test coverage for proposal acceptance, export, and write-back review.
   - Done in v0: add browser-level smoke test for chapter, scene, proposal, export, and References UI flow.
   - Done in P1-08: real-browser tests run against a live FastAPI backend and a temporary SQLite data root (`e2e/full-review-loop.e2e.mjs`, `e2e/wiki-failure.e2e.mjs`). Next: broaden edge-case coverage.

14. Unified review state machine (improvement plan Phase 3)
   - Done in P1-01: one shared transition model (`backend/app/review/state_machine.py`) for every reviewable object: `pending_review -> accepted | rejected | superseded`; decided states are terminal.
   - Done in P1-01: manuscript proposals, write-back proposals, and reference suggestions all enforce the machine; illegal moves return HTTP 409, unknown records 404, malformed requests 422.
   - Done in P1-01: accepting a manuscript proposal supersedes sibling pending proposals for the same scene; accepting a Canon update supersedes sibling updates for the same record.
   - Done in P1-02: write-back supports `action="update"` for existing Canon records with `target_record_id`, optimistic `expected_version`, field-level before/after `changes`, plus `version` / `updated_at` on Canon entities.
   - Done in P1-02: the frontend shows current value vs. proposed value, target record with versions, evidence excerpt from the source revision, and a conflict warning that blocks acceptance when the record changed.
   - Done in P1-03: every creation route validates proposals against current data before insert (structure, target existence, expected version, duplicate Canon names), so any created proposal can be accepted unless data changes concurrently.
   - Done in P1-03: Memplace prose samples are capped excerpts (2,000–6,000 character band) pointing at the authoritative revision instead of full-manuscript copies.
   - Done in P1-04: idempotent analysis runs (`analysis_runs` table keyed by project, source, processor, input hash); repeated unchanged requests replay stored results, explicit re-runs bump the run version and supersede still-pending prior proposals, failed runs are recorded and retried.

15. Consistency report with evidence (improvement plan Phase 4)
   - Done in P1-06: structured `ConsistencyFinding` model (severity, rule code, evidence excerpt, canon field, expected vs. observed, suggested action, confidence) with `POST`/`GET` `/projects/{id}/analysis/consistency/from-revision/{revision_id}` endpoints.
   - Done in P1-06: deterministic local rules — forbidden-fact verbatim mention (critical), Canon constraint capability used in prose (warning), required Canon missing from prose (warning), POV name absent while other entities are named (info); every finding carries the matched prose excerpt as evidence.
   - Done in P1-06: the checker runs through `AnalysisService.run_consistency_analysis`, so unchanged inputs replay the stored run (`X-Analysis-Cached: true`), explicit re-runs bump the run version on one lineage row, and changed Scene Contract / Canon / revision inputs generate a fresh run.
   - Done in P1-06: Revision History shows a Consistency action per accepted revision plus an evidence-backed findings panel (severity chips, expected/observed, source excerpt, suggested action).

16. Automatic post-acceptance analysis (improvement plan Phase 4)
   - Done in P1-07: accepting a manuscript proposal creates one Wiki-index job plus one consistency-analysis and one write-back-analysis job per created revision, all inside the acceptance transaction with revision-id idempotency keys.
   - Done in P1-07: the outbox dispatcher gained a job context (Wiki port, data store, cognition registry), so analysis handlers reuse the exact P1-06 checker and P1-04 idempotent generation paths instead of duplicating logic; provider-backed semantic rules can join later as new processors.
   - Done in P1-07: generated write-back proposals stay pending_review (analysis is automatic; acceptance is not), failed jobs are retried through the existing outbox retry route without duplicates, and the accept response reports outcomes via X-Wiki-Index-Status / X-Analysis-Job-Status headers.
   - Done in P1-07: Revision History shows a Post-Acceptance Analysis panel with live job status chips, refresh, and retry actions, and loads the finished report automatically after acceptance.
   - Done in P1-08: real browser E2E against a live backend covers accept -> auto-analysis -> review -> write-back acceptance, backend-restart persistence, and a wiki-failure path with UI retry recovery.

17. Architecture refactor (improvement plan Phase 5)
   - Done in P2-01: routers import no provider runtime types (`DeepSeekSettings`, OpenAI SDK, `HermesAgentClient`, `LocalFileLlmWiki`); they parse requests, call services, map domain errors to status codes, and set analysis/outbox headers.
   - Done in P2-01: application services own orchestration — Snowflake generation plus Wiki-index dispatch, reference suggestions, write-back review, Hermes processing, and provider-backed generation live in `app.services.*` with FastAPI wiring at module edges.
   - Done in P2-02: one `WritingProvider` protocol (`generate_snowflake`, `generate_manuscript`, `generate_reference`, `generate_writebacks`) in `app.integrations.provider_registry`; `LocalDeterministicProvider` and `DeepSeekProvider` register on the default registry with explicit priority resolution and typed configuration errors.
   - Done in P2-02: workflow runtime status is derived from registry state instead of router-level env reads; the external Hermes agent server is reachable only through the `app.integrations.hermes` port.
   - Done in P2-03: ten focused repositories under `app.data.repositories` coordinated by an explicit `SqliteUnitOfWork`; multi-aggregate flows run in `app.data.flows` inside single transactions, the store facade keeps every public signature, and schema creation lives in `app.data.schema`.
   - Done in P2-04: the frontend workspace store is split into seven domain stores plus an `/api` client layer; `workspace.ts` slims to selection, runtime status, and cross-store coordination while component templates stay untouched.

## Structured Snowflake compiler (improvement plan Phase 4)
   - Done in P1-05: deterministic Step 7 Canon Extractor parses the saved character bible into Canon create / update write-back proposals (existing records are matched by name; updates carry expected_version plus before/after changes), reusing the unified write-back review flow for acceptance.
   - Done in P1-05: deterministic Step 8 Scene Contract Parser turns the saved scene list into persisted Scene Proposals with sequence, chapter hint (resolved to chapter ids at parse time), POV, goal, conflict, turning point, resolved required-canon ids, forbidden facts, and open threads; structural problems (missing core fields, duplicate sequence numbers, TBD placeholders, unresolved canon or chapter references) surface as per-proposal parse warnings.
   - Done in P1-05: compile endpoints POST /projects/{id}/snowflake/artifacts/7/compile-canon-proposals and .../8/parse-scene-proposals are idempotent through the P1-04 analysis_runs table - unchanged inputs replay stored proposals, forced re-runs supersede stale pending proposals of the same source inside one transaction.
   - Done in P1-05: unparseable artifacts record a failed run and return HTTP 422 without writing any rows; the raw artifact always stays the authoritative source.
   - Done in P1-05: batch acceptance POST .../snowflake/scene-proposals/accept creates all selected scene contracts inside one SQLite transaction with pre-validation (sequence conflicts against existing contracts and inside the batch, chapter ownership), so a single conflict rolls back the whole batch; individual proposal status moves follow the shared review state machine (409 on illegal transitions).
   - Done in P1-05: the Snowflake workspace gains a compiler panel for steps 7 and 8 showing run versions, create/update counts, parse warnings, and a selectable scene-proposal table with accept-selected / accept-all-pending / reject actions.

## Interface Direction

The backend API should call a `WritingWorkflow` interface. A concrete workflow may internally use multiple `WorkflowAgent` implementations:

- pre-generation: context loader, canon checker, memory retriever, prompt planner
- generation: draft generator
- post-generation: consistency reviewer, style reviewer, artifact normalizer

The FastAPI router should not depend directly on LangChain, LangGraph, OpenAI SDK, or any other runtime-specific type.

The backend calls LLM Wiki only through `backend/app/llm_wiki/interfaces.py`. It exchanges staged source documents, sourced context results, and advisory insights; it never sends project snapshots, Canon records, Memory records, cognition registries, or provider configuration. Memplace and Infra Graph remain separate cognition/analysis modules.

## Product Modules

- **Snowflake**: planning compiler and artifact workflow.
- **Canon**: confirmed story facts and constraints.
- **Memory / Style**: prose memory, summaries, voice and rhythm samples.
- **Graph**: relationship and structure analysis.
- **LLM Wiki**: replaceable knowledge backend for staged content ingestion, sourced constraint retrieval, and advisory insights.
- **Cognition Modules**: project-scoped Memplace and Infra Graph helpers.
- **Manuscript**: chapters, scenes, drafts, revisions, and review.
- **Agent Orchestration**: workflow agents with traceable outputs and app-owned commits.

## Verification

Each increment should pass:

- backend import or route-level smoke check
- backend `unittest` coverage for changed data workflows
- frontend `pnpm build`
- Git working tree review before commit
