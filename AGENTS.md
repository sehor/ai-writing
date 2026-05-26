# AGENTS.md

This file guides Codex and other AI coding agents working on AI Writing Studio.

## Mission

Build a local-first long-form fiction workspace around the Snowflake Method. The product should preserve project state, canon, memory, style, graph structure, and human-reviewed AI changes. Do not turn it into a generic chatbot.

## Current Stack

- Frontend: Vite + Vue 3 + TypeScript
- Backend: Python + FastAPI
- Persistence: SQLite through Python `sqlite3`
- Development style: frontend/backend separated, local-first first

## Product Principles

- Snowflake artifacts are the planning backbone.
- Canon is a database of confirmed story facts, not ordinary notes.
- Memory/style is for continuity of prose, not fact correctness.
- Graph/structure analysis finds narrative gaps, but humans decide whether a gap is intentional.
- AI agents propose changes; the app validates and commits them.
- Prefer structured records over opaque prose when later steps must depend on the data.

## Engineering Rules

- Keep changes small and directly tied to the current task.
- Preserve the FastAPI router -> service/data/workflow boundary.
- Do not couple API routers directly to a model SDK, LangChain, LangGraph, or provider-specific types.
- Add persistence through `app.data` or a small adjacent module; avoid hidden global state.
- Keep frontend state local and explicit until a real state manager is justified.
- Do not add a large dependency without a concrete feature needing it now.
- Do not implement real AI generation before the workflow state shape and review contract are stable.

## Backend Conventions

- Pydantic request/response models live in `backend/app/models.py` until the file becomes too large.
- SQLite access lives behind `WritingDataStore` in `backend/app/data.py`.
- Routers validate project existence before mutating project-scoped records.
- Workflow runtime abstractions live under `backend/app/agents/`.
- Concrete AI runtimes must implement `WritingWorkflow` and return traceable stages.

## Frontend Conventions

- Keep the first screen a usable author workspace, not a landing page.
- Maintain the left navigation model: Snowflake, Canon, Memory, Graph, Manuscript.
- Disabled sections are acceptable only when the backend surface does not exist yet.
- Prefer dense, work-focused UI over marketing-style panels.
- When adding a domain feature, show its status and save/review state clearly.

## Implementation Order

1. Canon DB foundation. Done in v0.
2. Structured Scene Contracts. Done in v0.
3. Chapter Compiler v0 without real AI calls. Done in v0.
4. Deterministic local workflow runtime. Done in v0.
5. Memory/style store. Done in v0.
6. Graph/structure analysis.
7. Provider-backed AI workflow runtime.
8. Manuscript/version review workflow.

## Verification

Run relevant checks before calling work complete:

```bash
python -m compileall backend\app
cd frontend
pnpm build
```

If dependencies are not installed, report that clearly instead of pretending verification passed.
