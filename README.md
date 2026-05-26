# AI Writing Studio

AI Writing Studio is a local-first long-form fiction workspace. It is not meant to be a generic AI chat box. The product goal is to help an author grow a novel from Snowflake-method planning into manuscript drafts while preserving canon, memory, style, structure, and reviewable AI changes.

The current implementation is a local MVP: Vite + Vue 3 frontend, FastAPI backend, SQLite persistence, project creation, Snowflake steps, per-step artifact saving, Canon DB, Memory / Style records, Scene Contracts, Chapter Compiler v0, Graph / Structure v0, Manuscript review, write-back review, project-scoped cognition modules, and a deterministic local workflow runtime.
When `DEEPSEEK_API_KEY` is available in `.env`, Snowflake draft generation, provider manuscript proposal generation, and provider write-back suggestion generation use the DeepSeek OpenAI-compatible API runtime. The active workflow runtime is exposed in the author workspace.

## Product Thesis

Long-form AI writing breaks down when the system treats each prompt as an isolated generation task. The application should instead maintain durable creative state:

- **Project / Manuscript**: works, volumes, chapters, scenes, drafts, revisions, and version history.
- **Canon DB**: confirmed facts about characters, places, items, factions, rules, timelines, and forbidden knowledge.
- **Memory / Style**: original prose excerpts, chapter summaries, character voice samples, scene style, and narrative rhythm.
- **Graph / Structure**: relationships between characters, events, themes, locations, foreshadowing, and unresolved threads.
- **Chapter Compiler**: a repeatable pipeline that turns scene contracts into prose, checks the result, and proposes state updates.
- **Cognition Modules**: project-scoped LLM Wiki, Memplace, and structure modules that prepare context and ingest confirmed writing through app-owned interfaces.
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

## Cognition Module Boundary

LLM Wiki, Memplace, and Infra Graph can be built into the app, but they are isolated modules rather than main workflow logic. The core writing app exchanges structured data with them:

```text
Writing starts:
Core App -> cognition.prepare_context(project_id, writing_scope)
Cognition Modules -> ContextPacket[]
Writing Agent -> draft/proposal

Writing is confirmed:
Core App -> cognition.ingest_committed_content(project_id, content_event)
Cognition Modules -> ModuleReport[] + WritebackProposal[]
Core App -> validation + human review + commit
```

Each module owns its project-scoped data under `backend/data/projects/{project_id}/modules/`:

- `llm_wiki/`: `SCHEMA.md`, `index.md`, `log.md`, raw confirmed text, entities, concepts, comparisons, queries, and exported project pages.
- `memplace/`: prose samples and style/continuity material used to stabilize later generation.
- `infra_graph/`: structure analysis logic and future graph-derived reports.

Canon remains the app-owned database of confirmed story facts. LLM Wiki entities and Memplace samples can suggest updates, but only reviewed write-back proposals can mutate Canon or app Memory records.

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
- Cognition module boundary for LLM Wiki, Memplace, and Infra Graph context exchange.
- Provider-backed manuscript proposal generation from Scene Contracts when configured.
- Manuscript proposal review UI with accepted scene drafts and revision history.
- Direct editing for accepted manuscript scene drafts with revision preservation.
- Manuscript revision diff and restore UI.
- Markdown export for accepted manuscript scenes.
- Canon / Memory write-back proposal generation and review UI.
- Backend unit coverage for manuscript edit versioning.
- Frontend Snowflake workbench.
- Workflow interface boundary with declared pre-generation, generation, and post-generation agents.

Not yet implemented:

- Full chapter/manuscript organization beyond scene-level editing.
- Frontend interaction test coverage.
- Automated backend route tests and frontend interaction tests.
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
   - Next: add chapter-level manuscript organization and frontend interaction tests.

## Development

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
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

Use these checks after relevant changes:

```bash
python -m compileall backend\app
cd backend
.venv\Scripts\python -m unittest discover -s tests
cd frontend
pnpm build
```

See [AGENTS.md](AGENTS.md) for Codex development rules and [docs/development-plan.md](docs/development-plan.md) for the active implementation plan.
