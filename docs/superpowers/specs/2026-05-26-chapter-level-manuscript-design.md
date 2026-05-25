# Chapter-Level Manuscript Organization Design

## Purpose

AI Writing Studio currently stores scene contracts, manuscript proposals, accepted scene drafts, revisions, and write-back proposals, but manuscript organization is still scene-level. The next product increment adds a first-class chapter layer so the writing loop becomes:

```text
Snowflake scene contract -> chapter-organized scene -> proposal -> accepted manuscript scene -> revision -> write-back review -> chapter export
```

This keeps the product aligned with the PRD: long-form state management, Snowflake-backed drafting, and human-reviewed commits. This design intentionally does not add volumes, drag-and-drop sorting, provider refactors, or Copilot UI work.

## Decisions

- Add `Chapter` only; do not add `Volume`.
- A scene contract should normally belong to exactly one chapter.
- Existing scene contracts migrate into generated chapters in groups of five by `scene.sequence`.
- Chapter titles are simple generated labels during migration, such as `Chapter 1`; users can rename them later.
- Deleting a chapter never deletes scene contracts, manuscript proposals, accepted manuscript scenes, or revisions. It only makes linked scenes unassigned.

## Data Model

Add a SQLite table named `manuscript_chapters`:

```text
id          TEXT PRIMARY KEY
project_id  TEXT NOT NULL
sequence    INTEGER NOT NULL
title       TEXT NOT NULL
summary     TEXT NOT NULL DEFAULT ''
status      TEXT NOT NULL DEFAULT 'active'
created_at  TEXT NOT NULL
updated_at  TEXT NOT NULL
```

Constraints:

- `(project_id, sequence)` is unique.
- `project_id` references `projects(id)`.
- `status` starts as a lightweight string with expected values `draft`, `active`, and `archived`.

Extend `scene_contracts` with:

```text
chapter_id TEXT NULL
```

The field remains nullable for migration safety and for the explicit unassigned state. API and UI should guide users toward assigning every active scene to a chapter.

## Backend API

Add chapter CRUD endpoints under the existing manuscript router:

```text
GET    /api/projects/{project_id}/manuscript/chapters
POST   /api/projects/{project_id}/manuscript/chapters
PUT    /api/projects/{project_id}/manuscript/chapters/{chapter_id}
DELETE /api/projects/{project_id}/manuscript/chapters/{chapter_id}
```

Extend existing scene create/update models to include `chapter_id`.

Deleting a chapter sets `scene_contracts.chapter_id = NULL` for linked scenes and then deletes the chapter record. It does not cascade into manuscript state.

Update manuscript export so accepted scenes are grouped by chapter:

```markdown
# Project Title

## Chapter 1

### Scene Title

Scene content...
```

Ordering:

1. Chapter `sequence`
2. Scene contract `sequence`
3. Scene title as a stable fallback
4. Unassigned scenes at the end under `## Unassigned`

## Migration

Migration runs from `SQLiteWritingDataStore.init()` and must be idempotent:

1. Create `manuscript_chapters` if it does not exist.
2. Add `scene_contracts.chapter_id` if it does not exist.
3. For each project, select scenes with `chapter_id IS NULL`, ordered by `sequence ASC, id ASC`.
4. If the project has no chapters, create chapters from those scenes in groups of five.
5. If the project already has chapters, append new generated chapters after the current maximum chapter sequence for any still-unassigned scenes.
6. Assign each group of scenes to its generated chapter.

Generated chapter fields:

```text
sequence = next available chapter number
title = Chapter {sequence}
summary = Migrated from scene contracts {first_sequence}-{last_sequence}.
status = active
```

The migration never renames user-created chapters and never changes scenes that already have a `chapter_id`.

## Frontend Workflow

The Manuscript section becomes chapter-centered.

Chapter list:

```text
Chapter 1
  5 scenes
  3 accepted
Chapter 2
  4 scenes
  1 pending proposal
Unassigned
  2 scenes
```

Selected chapter panel:

- Edit chapter title, summary, and status.
- Show scene contracts in the selected chapter, ordered by scene sequence.
- Keep existing scene actions: compile, create proposal, provider proposal.
- Allow moving a scene to another chapter with a select control.
- Show unassigned scenes as a separate selectable group.

Review surfaces:

- Manuscript proposals default to the selected chapter's scenes, with a later option to show all proposals.
- Accepted manuscript scenes default to the selected chapter.
- Revision history defaults to the selected chapter.
- Canon / Memory write-back remains project-level, but revision-triggered actions retain scene and chapter context in source labels where available.

No drag-and-drop sorting in this increment. Sequence editing stays explicit and simple.

## Testing

Backend unit coverage:

- `init()` creates the chapter table and adds the nullable `chapter_id` field.
- Existing scenes migrate into chapters of five by `sequence`.
- Migration is idempotent and does not duplicate chapters.
- Scene create/update persists `chapter_id`.
- Deleting a chapter unassigns linked scenes without deleting those scenes.
- Markdown export groups accepted manuscript scenes by chapter and places unassigned scenes last.

Frontend verification:

- `pnpm build`

Full frontend interaction tests are not part of this increment. They remain a separate near-term milestone because the project does not yet have a frontend test runner.

## Risks

- `frontend/src/App.vue` is already large. The implementation should keep changes local, but small helper extraction is acceptable if it prevents the file from becoming harder to maintain.
- SQLite migration must be careful on existing local databases. It must check schema state before altering tables.
- Chapter deletion must not delete manuscript history.
- Export must remain useful for projects that still contain unassigned scenes.

## Out Of Scope

- Volume-level organization
- Drag-and-drop reordering
- Smart chapter naming
- Automatic chapter split/merge operations
- Provider runtime boundary refactor
- Reference/Copilot frontend integration
- Advanced graph visualization
