# Remediation execution

Approved order: backup safety and consistency; dependency and test baseline;
CLP / Outbox / Review; editable AI drafts; only the architecture and workspace
changes needed by those flows. The audit plan is evidence, not a requirement to
perform every proposed refactor.

## Acceptance criteria

1. Backup v2 includes every project table, reads one database snapshot, validates
   packages before mutation, rejects cross-project rows and unsafe paths, and
   rolls back both database and module files on an import failure. Legacy v1
   packages are explicitly incomplete and cannot replace an existing project.
2. `uv sync --frozen --extra dev` provides the real backend dependencies. Backend
   and frontend checks run from the documented environment. Behavior tests cover
   the broken flows; browser tests wait for the relevant jobs' terminal states.
3. All four post-commit jobs remain visible across project reloads, update without
   manual refresh, and retry through the dispatcher. Narrative review uses the
   actual target's conflict rules and refreshes accepted results.
4. An author can edit an AI proposal before committing one official revision.
   The original proposal stays immutable; unsaved edits retain draft protection.
5. Share only the orchestration actually duplicated by these flows. Preserve the
   existing repositories, transaction boundaries, human review, and local-first
   architecture. Do not mechanically split files by line count.

## Validation

- Backend: `uv run --frozen --extra dev python -m unittest discover -s tests -q`,
  `uv run --frozen --extra dev python -m compileall app`,
  `uv run --frozen --extra dev ruff check .`,
  `uv run --frozen --extra dev ruff format --check .` (from `backend`).
- Frontend: `pnpm test`, `pnpm lint`, `pnpm build`, and real-backend E2E
  (from `frontend`). All browser and destructive failure tests use temporary data.
- Never use a user's existing project database for regression fixtures.

## Implemented (2026-08-31)

- Backup v2 covers all 20 project tables, including the six narrative tables.
  Export uses one SQLite read snapshot; import preflights package bounds, paths,
  project identities, JSON, SQL constraints and the application's record readers.
  Module files are staged, originals retained until commit, and ordinary failures
  compensate both stores. Case aliases and orphaned module directories cannot
  silently overwrite author data. V1 can import into an empty target but cannot
  overwrite an existing target; the UI explains its incomplete coverage.
- Backend runtime dependencies now come from `pyproject.toml` / `uv.lock`;
  `requirements.txt` is a checked generated compatibility export. Local and CI
  commands use the same environment. Existing Ruff baseline issues were fixed.
  Vitest, Pinia and Vue component behavior tests supplement source-boundary tests.
- All four revision jobs, including CLP, are visible after reload. Polling stops
  at terminal states, aborts on project switch, retains useful failure UI, and
  refreshes reports/proposals on completion. Retry returns 202/pending and wakes
  the dispatcher; it never executes the handler inline. Lists are bounded and
  support loading up to 500 recent revision jobs.
- StoryThread reviews compare lifecycle states rather than Canon versions.
  NarrativeRelation and CLP evidence have dedicated review displays; unknown
  targets cannot be accepted. Accepted narrative results refresh the read-only
  threads/relations/Director view in Graph.
- AI proposals have separate editable, project-scoped local drafts. Acceptance
  preserves the AI original and atomically commits the author's text as exactly
  one revision with four jobs. Repeated acceptance is idempotent. Version conflicts
  keep the draft, show current official text, and require an explicit author
  acknowledgment before rebasing. Refresh and project switches retain local drafts.
- One shared post-commit refresh action serves acceptance, manual save and restore.
  The workspace separates prose, references and review, with collapsible setup and
  context. Project loading temporarily disables editing to prevent late responses
  from overwriting fresh input. Existing repositories and service boundaries remain.

## Verification results

- Backend: **224 tests passed**, including 21 backup tests and edited-draft/API tests.
- Frontend: **27 source-boundary checks + 13 behavior tests passed**.
- Ruff check / format check, compileall, ESLint, Vue type check, production build,
  generated requirements comparison and `git diff --check`: passed.
- Real-backend browser suites passed: full review loop and wiki-failure recovery.
  The full loop covers editable-draft reload, four automatic jobs without manual
  refresh, Canon/StoryThread/NarrativeRelation review, export, restart, manual edit
  and restore. Every fixture uses a temporary data root and deterministic local
  generation; no paid provider calls are needed.
- Stability: both browser suites passed two further consecutive runs after the
  final changes. The Vite teardown timer now cancels after a successful close,
  eliminating misleading timeout messages and the lingering timer.

## Explicit limits / deferred work

- The filesystem coordination lock supports one backend process (the current
  local-first deployment). Multiple server workers/processes need a shared lock.
- Compensating rollback covers reported exceptions, including commit and rename
  failures. It is **not a power-loss/process-kill recovery journal**. A hard stop
  during the directory swap may leave `.restore-*` with original module files;
  stop the application and preserve those directories for manual recovery.
- Full OpenAPI-generated frontend types, a repository-wide store rewrite, a rich
  text editor, Copilot Apply and a complete workstation redesign are deferred.
  This pass supplies the usable draft/review workspace and necessary boundaries;
  those larger changes should follow concrete authoring needs.
