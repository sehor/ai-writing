# AI Writing Studio Development Plan

## Current Goal

Build a local-first long-form writing studio around the Snowflake Method. The backend should expose stable business APIs first, while AI generation remains behind project-owned interfaces so the implementation can later use direct model SDKs, LangGraph, or another workflow runtime without changing the API contract.

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

5. AI runtime implementation
   - Add one concrete `WritingWorkflow` implementation.
   - Start with direct SDK calls or LangGraph only after the workflow state shape is stable.
   - Add tracing for each agent step before exposing AI output in the UI.

## Interface Direction

The backend API should call a `WritingWorkflow` interface. A concrete workflow may internally use multiple `WorkflowAgent` implementations:

- pre-generation: context loader, canon checker, memory retriever, prompt planner
- generation: draft generator
- post-generation: consistency reviewer, style reviewer, artifact normalizer

The FastAPI router should not depend directly on LangChain, LangGraph, OpenAI SDK, or any other runtime-specific type.

## Verification

Each increment should pass:

- backend import or route-level smoke check
- frontend `pnpm build`
- Git working tree review before commit
