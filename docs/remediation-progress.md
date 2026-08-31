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

- First-pass backend: **224 tests passed**, including 21 backup tests and edited-draft/API tests.
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

## Follow-up: interrupted restore recovery

The first pass was committed as `18c24f1`. The follow-up adds persistent restore
journals and migration 8 (`backup_restore_commits`). This table records operational
commit decisions only and is deliberately excluded from project ZIP packages.

The journal is written before directory replacement and contains the operation,
project and database identities. Prepared file contents and journal writes are
flushed before committing. The restore transaction explicitly uses SQLite
`synchronous=FULL`; its marker commits together with the project rows. Recovery
runs before HTTP requests and the Outbox dispatcher start, and before another
import begins. Restores are serialized within the backend process.

| Durable evidence | Recovery decision |
| --- | --- |
| No commit marker, preparation only | Leave the original files; remove staging data |
| No commit marker, directory replacement begun | Restore the old directory, or remove only the uncommitted new directory |
| Commit marker present | Keep the new directory and finish removing the old copy |
| Rollback already completed | Clean remaining staging files without touching later author work |
| Invalid identity, damaged journal, missing committed files, or legacy unjournaled restore | Stop startup; preserve the evidence for manual recovery |

Recovery itself is restartable. The journal is removed last during cleanup, and
the database marker is removed only after filesystem cleanup. A failed commit
acknowledgment cannot roll files back after SQLite has committed. Cleanup failures
retain evidence and emit an operational log instead of misreporting core success.

Verification includes real child processes terminated with `os._exit` before
journal creation, after staging, after each directory rename, before/after commit,
and during cleanup; it also terminates recovery itself and restarts it. Other cases
cover first-time imports, startup ordering, invalid/foreign journals, missing files,
deferred cleanup, commit acknowledgments, and exclusion of operational markers from
ZIP exports. All use temporary databases and directories.

Follow-up final verification: **236 backend tests passed**, including 12 recovery
tests with multiple real process-termination checkpoints. The 40 frontend checks,
both real-browser E2E suites, Ruff check/format, compileall, ESLint, production build
and whitespace checks passed. Temporary E2E service ports were released.

## Explicit limits / deferred work

- The filesystem coordination lock supports one backend process (the current
  local-first deployment). Multiple server workers/processes need a shared lock.
- Process-kill/restart recovery is now implemented and tested. This is not a
  promise against arbitrary physical power loss, broken storage, or filesystem
  corruption. Python file fsync flushes file contents; portable directory fsync
  is not available on Windows. POSIX directory updates are explicitly synced.
  References: [Python fsync](https://docs.python.org/3/library/os.html#os.fsync)
  and [SQLite synchronous](https://www.sqlite.org/pragma.html#pragma_synchronous).
- Do not delete `.restore-*` folders or move the database while recovery is pending.
  On a startup recovery error, stop all backend processes, preserve a copy of the
  entire data root (including `app.db`, its WAL/SHM files, and restore directories),
  resolve storage/permission issues, then restart on the same path. Unknown legacy
  restore directories have no reliable commit marker and require manual inspection;
  never infer which copy to keep from modification times alone.
- Full OpenAPI-generated frontend types, a repository-wide store rewrite, a rich
  text editor, Copilot Apply and a complete workstation redesign are deferred.
  This pass supplies the usable draft/review workspace and necessary boundaries;
  those larger changes should follow concrete authoring needs.
