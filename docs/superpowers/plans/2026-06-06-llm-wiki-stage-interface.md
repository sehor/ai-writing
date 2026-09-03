# LLM Wiki Stage Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a stage-aware LLM Wiki interface that can be backed by a local module today and an external agent later, without exposing application snapshots, Canon, Memory, cognition modules, or model-provider configuration.

**Architecture:** The core app exchanges narrow Pydantic DTOs with an `LlmWiki` protocol. A local file-backed adapter owns its own project-scoped source documents and applies a Snowflake-stage policy for retrieval and insight generation. Application routers only translate saved Snowflake artifacts and accepted manuscript revisions into interface documents, and request context through the interface before generation.

**Tech Stack:** Python 3.11, Pydantic, FastAPI dependency injection, pathlib, unittest.

---

### Task 1: Stage Protocol

**Files:**
- Modify: `step-llm-wiki.md`
- Create: `backend/app/llm_wiki/stage_protocol.py`
- Test: `backend/tests/test_llm_wiki_interface.py`

- [x] **Step 1: Write failing stage-policy tests**

Test that planning stages retrieve only allowed upstream planned artifacts, Step 9 respects a bounded story scope, and Step 10 can retrieve observed manuscript evidence only up to its story position.

- [x] **Step 2: Run the focused test and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_llm_wiki_interface -v
```

Expected: import failure because `app.llm_wiki` does not exist.

- [x] **Step 3: Implement the stage-policy table**

Create immutable policy records with:

```python
step
artifact_type
planned_source_steps
include_observed
insight_kinds
```

- [x] **Step 4: Run the focused test and verify GREEN**

Run the same unittest command and expect all stage-policy tests to pass.

### Task 2: Interface Contract

**Files:**
- Create: `backend/app/llm_wiki/__init__.py`
- Create: `backend/app/llm_wiki/interfaces.py`
- Test: `backend/tests/test_llm_wiki_interface.py`

- [x] **Step 1: Write failing DTO and protocol tests**

Cover:

```python
WikiSourceDocument
WikiContextQuery
WikiContextResult
WikiInsightQuery
WikiInsightResult
WikiIngestionResult
LlmWiki
```

Assert that no DTO contains project snapshots, Canon records, Memory records, cognition registries, or provider settings.

- [x] **Step 2: Verify RED**

Run the focused unittest module and confirm the missing types cause the failure.

- [x] **Step 3: Implement the narrow interface**

Use only scalar metadata, content, evidence, constraints, and insight records. Mark source knowledge as `planned` or `observed`, and require `source_ref`, `version`, `status`, and optional story position.

- [x] **Step 4: Verify GREEN**

Run the focused unittest module and expect the contract tests to pass.

### Task 3: Local Adapter

**Files:**
- Create: `backend/app/llm_wiki/local_backend.py`
- Create: `backend/app/llm_wiki/dependencies.py`
- Test: `backend/tests/test_llm_wiki_interface.py`

- [x] **Step 1: Write failing local-adapter tests**

Test that:

- planned and observed documents are stored separately;
- superseded versions are not returned as active evidence;
- retrieval obeys the stage policy and story-position boundary;
- insights contain source references;
- the adapter does not access `WritingDataStore`.

- [x] **Step 2: Verify RED**

Run the focused unittest module and confirm the adapter is missing.

- [x] **Step 3: Implement minimal file-backed behavior**

Persist one JSON document per source under:

```text
backend/data/projects/{project_id}/modules/llm_wiki/sources/
```

Filter documents by stage, knowledge class, status, scope, story position, and supersession metadata. Return concise evidence excerpts and deterministic coverage/continuity insights.

- [x] **Step 4: Verify GREEN**

Run the focused unittest module and expect all adapter tests to pass.

### Task 4: Application Integration Through the Port

**Files:**
- Modify: `backend/app/agents/writing_workflow.py`
- Modify: `backend/app/agents/deepseek_workflow.py`
- Modify: `backend/app/routers/snowflake.py`
- Modify: `backend/app/routers/manuscript.py`
- Modify: `backend/app/routers/wiki.py`
- Test: `backend/tests/test_llm_wiki_integration.py`

- [x] **Step 1: Write failing integration tests**

Use a recording `LlmWiki` implementation through dependency injection and assert:

- saving a Snowflake artifact ingests a `planned` source tagged with its step;
- generating a Snowflake artifact requests context for that step;
- accepting or editing manuscript content ingests an `observed` revision;
- the app passes no snapshot, Canon, Memory, cognition object, or DeepSeek settings to the port.

- [x] **Step 2: Verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_llm_wiki_integration -v
```

- [x] **Step 3: Integrate only through `LlmWiki`**

Inject `LlmWiki` into workflow construction and relevant routers. Translate app records into `WikiSourceDocument` at the boundary. Keep existing Canon and Memory loading in the main application; merge returned Wiki evidence only as an additional context section.

- [x] **Step 4: Verify GREEN**

Run both new unittest modules and expect all tests to pass.

### Task 5: Migration and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/older/development-plan.md`
- Modify: existing tests only where old LLM Wiki snapshot behavior is intentionally superseded

- [x] **Step 1: Document the corrected ownership boundary**

State that LLM Wiki owns derived knowledge from staged content, while the app owns Snowflake records, Canon, Memory, Manuscript, provider configuration, and review state.

- [x] **Step 2: Run focused tests**

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_llm_wiki_interface backend.tests.test_llm_wiki_integration -v
```

- [x] **Step 3: Run backend regression tests**

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

- [x] **Step 4: Run compile verification**

```powershell
backend\.venv\Scripts\python.exe -m compileall backend\app
```

- [x] **Step 5: Review the final diff**

Confirm every application call to the new module uses only the `LlmWiki` interface and no local adapter type leaks into routers or workflows.
