# AI Writing Studio Development Plan

## Current Goal

Build a local-first long-form writing studio around the Snowflake Method. The backend should expose stable business APIs first, while AI generation remains behind project-owned interfaces so the implementation can later use direct model SDKs, LangGraph, or another workflow runtime without changing the API contract.

Canon DB v0, Memory / Style v0, structured Scene Contracts, Chapter Compiler v0, Graph / Structure v0, project-scoped cognition modules, deterministic local workflow, DeepSeek-backed Snowflake runtime, provider-backed manuscript proposals, Manuscript Proposal review v0, accepted manuscript scene state, chapter-level manuscript organization, direct scene editing, manuscript revision history, Markdown export, Canon / Memory write-back proposals, deterministic revision-based write-back suggestions, provider-backed write-back suggestions, structured References / Copilot UI, frontend review tools, frontend contract tests, browser smoke tests, backend route tests, backend edit-versioning tests, CI gates, LLM Wiki outbox, the unified review state machine with Canon-update write-backs, pre-persist proposal validation, idempotent analysis runs, the deterministic consistency report with evidence-backed findings, and the structured Snowflake compiler now exist.

Done in P1-05: Snowflake Step 7 artifacts compile into reviewable Canon create / update write-back proposals through a deterministic local extractor, and Step 8 artifacts parse into persisted Scene Contract proposals (sequence, chapter hint, POV, goal, conflict, turning point, required canon ids, forbidden facts, open threads) that carry their source excerpt and parse warnings.

The next implementation focus is **automatic post-acceptance analysis (P1-07)**: after accepting a manuscript proposal, enqueue a consistency-analysis job alongside the Wiki outbox job so reports appear without a manual trigger; provider-backed semantic rules stay behind the same processor interface.

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
   - Next: add browser interaction tests against a live backend and broaden edge-case coverage.

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
   - Next (P1-07): after accepting a manuscript proposal, enqueue a consistency-analysis job alongside the Wiki outbox job so reports appear without a manual trigger; provider-backed semantic rules (goal/conflict/turning-point embodiment, adjacent-revision state conflicts) stay behind the same processor interface.

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
