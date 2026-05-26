# AI Writing Studio Development Plan

## Current Goal

Build a local-first long-form writing studio around the Snowflake Method. The backend should expose stable business APIs first, while AI generation remains behind project-owned interfaces so the implementation can later use direct model SDKs, LangGraph, or another workflow runtime without changing the API contract.

The next implementation focus is **chapter-level manuscript organization and frontend interaction tests**. Canon DB v0, Memory / Style v0, structured Scene Contracts, Chapter Compiler v0, Graph / Structure v0, project-scoped cognition modules, deterministic local workflow, DeepSeek-backed Snowflake runtime, provider-backed manuscript proposals, Manuscript Proposal review v0, accepted manuscript scene state, direct scene editing, manuscript revision history, Markdown export, Canon / Memory write-back proposals, deterministic revision-based write-back suggestions, provider-backed write-back suggestions, manuscript diff / restore, frontend review tools, and backend edit-versioning tests now exist.

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

11. Cognition module boundary
   - Done in v0: add `backend/app/cognition/` interfaces for `ContextPacket`, `CommittedContentEvent`, `ModuleReport`, and project snapshots.
   - Done in v0: isolate LLM Wiki export/ingest logic in a project-scoped `llm_wiki` module.
   - Done in v0: isolate style sample ingestion in a project-scoped `memplace` module.
   - Done in v0: route scene compilation, manuscript proposal generation, Snowflake generation, and revision ingestion through cognition module interfaces.
   - Next: replace local module implementations with CLI/MCP/agent adapters without changing core app routes.

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
   - Next: add chapter-level manuscript organization.
   - Next: add frontend interaction tests for proposal acceptance, editing, export, and write-back review.

## Interface Direction

The backend API should call a `WritingWorkflow` interface. A concrete workflow may internally use multiple `WorkflowAgent` implementations:

- pre-generation: context loader, canon checker, memory retriever, prompt planner
- generation: draft generator
- post-generation: consistency reviewer, style reviewer, artifact normalizer

The FastAPI router should not depend directly on LangChain, LangGraph, OpenAI SDK, or any other runtime-specific type.

The backend API should also call cognition modules through `backend/app/cognition/` interfaces. LLM Wiki, Memplace, and Infra Graph modules may be local implementations today and external agent/MCP/CLI adapters later. Core app code should exchange only context packets, committed-content events, reports, and reviewable proposals with these modules.

## Product Modules

- **Snowflake**: planning compiler and artifact workflow.
- **Canon**: confirmed story facts and constraints.
- **Memory / Style**: prose memory, summaries, voice and rhythm samples.
- **Graph**: relationship and structure analysis.
- **Cognition Modules**: project-scoped LLM Wiki, Memplace, and Infra Graph adapters used for context preparation and confirmed-content ingestion.
- **Manuscript**: chapters, scenes, drafts, revisions, and review.
- **Agent Orchestration**: workflow agents with traceable outputs and app-owned commits.

## Verification

Each increment should pass:

- backend import or route-level smoke check
- backend `unittest` coverage for changed data workflows
- frontend `pnpm build`
- Git working tree review before commit
