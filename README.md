# AI Writing Studio

AI Writing Studio is a local-first long-form fiction workspace. It is not meant to be a generic AI chat box. The product goal is to help an author grow a novel from Snowflake-method planning into manuscript drafts while preserving canon, memory, style, structure, and reviewable AI changes.

The current implementation is a local MVP: Vite + Vue 3 frontend, FastAPI backend, SQLite persistence behind focused repositories coordinated by an explicit unit of work, domain-split frontend stores behind a slim workspace shell, project creation, Snowflake steps, per-step artifact saving, Canon DB, Memory / Style records, Scene Contracts, Chapter Compiler v0, Graph / Structure v0, Manuscript review, write-back review, project-scoped cognition modules, and a deterministic local workflow runtime.
When `DEEPSEEK_API_KEY` is available in `.env`, Snowflake draft generation, provider manuscript proposal generation, and provider write-back suggestion generation use the DeepSeek OpenAI-compatible API runtime. The active workflow runtime is exposed in the author workspace.

## Product Thesis

Long-form AI writing breaks down when the system treats each prompt as an isolated generation task. The application should instead maintain durable creative state:

- **Project / Manuscript**: works, volumes, chapters, scenes, drafts, revisions, and version history.
- **Canon DB**: confirmed facts about characters, places, items, factions, rules, timelines, and forbidden knowledge.
- **Memory / Style**: original prose excerpts, chapter summaries, character voice samples, scene style, and narrative rhythm.
- **Graph / Structure**: relationships between characters, events, themes, locations, foreshadowing, and unresolved threads.
- **Chapter Compiler**: a repeatable pipeline that turns scene contracts into prose, checks the result, and proposes state updates.
- **Narrative Domain / Snapshot**: SQLite-backed authoritative story facts, knowledge state, threads, relations, and scene-safe retrieval.
- **LLM Wiki source adapter**: a replaceable derived store for staged planning/prose evidence; it does not own story facts or relationships.
- **Cognition Modules**: project-scoped style and structure helpers such as Memplace and Infra Graph.
- **Agent Orchestration**: multiple narrow AI agents coordinated by the app, with the app retaining final write/commit authority.

The moat is not a model call. The moat is **state management + creative workflow + AI write-back review**.

## Snowflake Method as Compiler

The Snowflake Method is the central workflow engine. Each step produces a structured artifact that later systems can read, validate, and compile.

| Step | Artifact | Purpose |
|---:|---|---|
| 1 | `story_contract` | One-sentence story promise |
| 2 | `plot_seed` | One-paragraph beginning, middle, end |
| 3 | `character_seeds` | Initial goals, conflicts, secrets, arcs |
| 4 | `plot_synopsis` | One-page causal outline |
| 5 | `character_pov_lines` | Story from each major character viewpoint |
| 6 | `expanded_plot` | Expanded multi-page plot |
| 7 | `canon_entities` | Character/location/item/faction facts for Canon |
| 8 | `scene_contracts` | Scene goals, conflicts, turns, constraints |
| 9 | `expanded_scenes` | Detailed scene beats and chapter plans |
| 10 | `manuscript` | Draft prose generated from contracts and constraints |

The intended loop is:

```text
Snowflake artifact
-> Canon constraints
-> Memory/style context
-> Graph/structure checks
-> Draft or plan generation
-> Consistency and quality review
-> Human-approved commit
```

## Architecture

```text
frontend/   Vite + Vue 3 + TypeScript
backend/    FastAPI application and business APIs
storage/    SQLite for local development, later Markdown/JSON export
agents/     Workflow interfaces first; runtime implementation later
docs/       Development plan and architecture notes
```

The backend owns workflow state and persistence. The frontend owns author-facing review and editing. AI agents should never write final project state directly; they propose changes that the app validates and commits.

## Narrative Authority and LLM Wiki Source Boundary

SQLite Narrative Domain is the only authoritative story state. `NarrativeSnapshot.for_scene(...)` assembles scene-safe facts, knowledge visibility, Narrative Graph relations, Story Threads, accepted prior manuscript, and Memory / Style from application-owned state. Scene / Manuscript generation does not ask LLM Wiki to decide what is true or visible.

The old LLM Wiki path remains only as a replaceable source/evidence adapter behind `backend/app/llm_wiki/interfaces.py`:

```text
Approved planning or prose:
Core App -> llm_wiki.ingest(WikiSourceDocument)
LLM Wiki -> WikiIngestionResult

Snowflake planning asks for staged source evidence:
Core App -> llm_wiki.retrieve_context(WikiContextQuery)
LLM Wiki -> WikiContextResult with source excerpts only

Scene / Manuscript generation:
SQLite Narrative Domain -> Narrative Graph projection -> NarrativeSnapshot
```

The local adapter stores project-scoped source JSON plus readable Markdown mirrors under `backend/data/projects/{project_id}/modules/llm_wiki/sources/`. It preserves planned/observed separation, supersession, stage visibility, and deterministic evidence ranking, but it no longer builds a second `wiki/concepts` knowledge projection or turns source excerpts into local fact constraints. The legacy context/insight HTTP surface remains advisory/compatible; it is not an authority for Canon or Narrative Relations.

LLM Wiki CLP is a separate local sidecar adapter: accepted manuscript revisions may produce typed candidates with evidence, but candidates must pass application validation and human Review before any SQLite Narrative Domain mutation. Memplace and Infra Graph remain under separate cognition/analysis boundaries.

## Current State

Implemented:

- Project listing and creation.
- SQLite-backed local persistence.
- Snowflake step definitions.
- Snowflake artifact save/load per project and step.
- Canon DB v0 with typed entities, SQLite persistence, APIs, and a frontend panel.
- Memory / Style v0 with chapter summaries, prose samples, voice samples, and style rules.
- Scene Contracts with structured goal/conflict/turning-point records.
- Chapter Compiler v0 that assembles scene context, draft placeholders, and review checklists.
- Deterministic local workflow generation with trace output.
- DeepSeek-backed Snowflake generation through the workflow interface when configured.
- Workflow runtime status API and frontend runtime indicator.
- Graph / Structure v0 with nodes, edges, unresolved threads, and structural risk review.
- Stage-aware LLM Wiki source/evidence interface with replaceable local/external implementations; scene authority stays in Narrative Snapshot / SQLite.
- Cognition module boundary for Memplace and Infra Graph context exchange.
- Provider-backed manuscript proposal generation from Scene Contracts when configured.
- Manuscript proposal review UI with accepted scene drafts and revision history.
- Chapter-level manuscript organization for grouping Scene Contracts and accepted drafts.
- Direct editing for accepted manuscript scene drafts with revision preservation.
- Manuscript revision diff and restore UI.
- Markdown export for accepted manuscript scenes.
- Canon / Memory write-back proposal generation and review UI.
- Structured References / Copilot UI for reviewable writing suggestions.
- Outbox-backed LLM Wiki indexing: core saves commit first, wiki ingest failures surface as retryable jobs (`GET /api/projects/{id}/outbox-jobs`, `POST .../outbox-jobs/{job_id}/retry`) instead of failed requests.
- Unified review state machine: every reviewable object moves `pending_review -> accepted | rejected | superseded`; decided states are final and illegal changes return HTTP 409.
- Write-back updates for existing Canon records with optimistic version checks: the UI shows current vs. proposed values, evidence from the source revision, and a conflict warning when the record changed after proposal creation.
- Pre-persist write-back validation: proposals are checked against current data (structure, target record, expected version, duplicate names) before insertion.
- Idempotent analysis runs: repeated unchanged analysis requests replay stored results instead of duplicating proposals; explicit re-runs supersede stale pending proposals and bump the run version.
- Automatic post-acceptance analysis: accepting a manuscript proposal schedules the consistency report and deterministic write-back suggestions as outbox jobs, so findings and pending review items appear without a manual trigger while acceptance of them stays a human decision.
- Deterministic consistency report with evidence-backed findings (forbidden facts, forbidden capabilities, missing required Canon, absent POV) surfaced in Revision History.
- Draft safety on the frontend: editors autosave to a local draft cache, confirm before switching away, restore cached drafts, and flush on page close; async generations are bound to project/step request scopes.
- Backend unit coverage for manuscript edit versioning.
- Backend route test coverage for the manuscript/write-back review loop.
- Frontend contract test coverage for the References UI.
- Browser-level frontend smoke coverage for the chapter / scene / proposal / export / reference flow.
- Frontend Snowflake workbench.
- Workflow interface boundary with declared pre-generation, generation, and post-generation agents.
- Provider registry (`backend/app/integrations/provider_registry.py`): deterministic local and DeepSeek backends register behind one `WritingProvider` interface; Hermes stays an isolated external-agent port.
- Routers as a pure HTTP layer over application services (`backend/app/services/`): request parsing, service calls, domain-error mapping, and response headers only.
- Focused data layer (P2-03): ten repositories under `backend/app/data/repositories/` over one schema module, an explicit `SqliteUnitOfWork` owning the connection and transaction boundary, and cross-aggregate flows (`app.data.flows`) that keep acceptance / restore / apply operations atomic; the store facade keeps every public signature.
- Domain-split frontend stores (P2-04): `stores/{projects,snowflake,canon,memory,manuscript,reviews,graph}.ts` plus a typed `/api` client; `workspace.ts` keeps selection, runtime status, and cross-store coordination only.
- Real-browser E2E (P1-08): Playwright Chromium drives the live FastAPI backend over a temporary SQLite root with zero route mocking — full accept -> auto-analysis -> review -> write-back loop, backend-restart persistence, and wiki-failure recovery through the UI retry (`e2e/`, see its README).

Not yet implemented:

- Advanced graph visualization beyond tabular structure analysis.

## Near-Term Build Order

1. **Canon DB foundation**
   - Implemented v0: typed entities for characters, locations, items, factions, and rules.
   - Implemented v0: current state, constraints, last seen, and timeline notes.
   - Implemented v0: CRUD APIs and a basic frontend panel.

2. **Scene Contracts**
   - Implemented v0: structured scene records.
   - Implemented v0: POV, goal, conflict, turn, required canon, forbidden facts, and open threads.

3. **Chapter Compiler v0**
   - Implemented v0: load one scene contract plus related Canon.
   - Implemented v0: produce a draft placeholder and context package.
   - Implemented v0: return a consistency checklist before any real AI integration.

4. **AI Workflow Runtime**
   - Implemented v0: deterministic local `WritingWorkflow` implementation.
   - Keep model SDK choices behind the workflow interface.
   - Implemented v0: trace output for every agent step.

5. **Memory / Style and Graph**
   - Implemented v0: style samples, chapter summaries, voice samples, and style rules.
   - Implemented v0: Memory / Style context is loaded into workflow and chapter compiler output.
   - Implemented v0: lightweight graph extraction before advanced GraphRAG.

6. **Provider-backed workflow runtime**
   - Implemented v0: DeepSeek OpenAI-compatible runtime behind the `WritingWorkflow` interface.
   - Implemented v0: runtime status is visible in the frontend.
   - Implemented v0: Scene Compiler output can be saved as a manuscript proposal.
   - Implemented v0: proposals have pending, accepted, and rejected review states.
   - Implemented v0: accepted proposals write into current manuscript scene drafts with version numbers.
   - Implemented v0: each accepted proposal is preserved in manuscript revision history.
   - Implemented v0: Canon and Memory write-back proposals can be accepted or rejected through backend APIs.
   - Implemented v0: backend can generate deterministic Canon / Memory write-back suggestions from accepted manuscript revisions.
   - Implemented v0: backend can ask the configured DeepSeek runtime for structured Canon / Memory write-back suggestions.
   - Implemented v0: backend can diff manuscript revisions and restore a revision as a new current version.
   - Implemented v0: frontend review UI for write-back proposals and manuscript diff / restore.
   - Implemented v0: provider-backed manuscript proposals from Scene Contracts.
   - Implemented v0: Markdown export for accepted manuscript scenes.
   - Implemented v0: direct accepted manuscript scene editing with revision history.
   - Implemented v0: backend unit tests for manuscript edit versioning.
   - Implemented v0: chapter-level manuscript organization for Scene Contracts and exports.
   - Implemented v0: structured References / Copilot UI for reviewable suggestions.
   - Implemented v0: zero-dependency frontend contract test for References UI wiring.
   - Implemented v0: backend route test for manuscript proposal acceptance, export, and Canon write-back.
   - Implemented v0: browser-level smoke test for the frontend review flow with mocked API routes.
   - Implemented in P1-08: real-browser E2E against a live backend and temporary SQLite root (`e2e/full-review-loop.e2e.mjs`, `e2e/wiki-failure.e2e.mjs`). Next: broaden edge-case coverage.

## Development

Backend:

```bash
cd backend
uv run --with-requirements requirements.txt uvicorn app.main:app --reload --port 8000
```

AI runtime configuration lives in the repository `.env` file:

```bash
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL_FOR_OPENAI=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
```

The DeepSeek workflow keeps stable project, Canon, Memory / Style, and prior Snowflake context at the front of the message list, with the current author instruction last. This preserves a repeatable prefix so DeepSeek prompt caching can be reused across nearby generation calls.

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Open the frontend at `http://127.0.0.1:5173`.

## Verification

Use these checks after relevant changes (CI runs the same gates via [.github/workflows/verify.yml](.github/workflows/verify.yml)):

```bash
# Backend
python -m compileall backend/app
pip install ruff==0.16.4
ruff check backend
ruff format --check backend
cd backend
python -m unittest discover -s tests
cd ..

# Frontend
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm test
pnpm build
```

Browser E2E (optional, local only — boots a real backend on a temporary SQLite root plus Vite, then drives Chromium):

```bash
cd e2e
node full-review-loop.e2e.mjs   # happy path: accept -> auto-analysis -> review -> write-back -> restart persistence
node wiki-failure.e2e.mjs       # wiki ingest failure + UI retry recovery
```

See [AGENTS.md](AGENTS.md) for Codex development rules and [docs/development-plan.md](docs/development-plan.md) for the active implementation plan.
