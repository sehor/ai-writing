<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useWorkspaceStore } from '../stores/workspace'

const store = useWorkspaceStore()
const {
  sceneContracts,
  manuscriptChapters,
  manuscriptProposals,
  manuscriptScenes,
  manuscriptRevisions,
  writebackProposals,
  referenceSuggestions,
  hermesProcessReport,
  activeSection,
  activeChapterId,
  activeSceneId,
  activeProposalId,
  activeWritebackId,
  activeReferenceId,
  diffLeftRevisionId,
  diffRightRevisionId,
  editingManuscriptSceneId,
  isSavingScene,
  isDeletingScene,
  isSavingChapter,
  isDeletingChapter,
  isCompilingScene,
  isCreatingProposal,
  isCreatingProviderProposal,
  isUpdatingProposal,
  isSavingManuscriptScene,
  isExportingManuscript,
  isLoadingDiff,
  isRestoringRevision,
  isCreatingWriteback,
  isCreatingProviderWriteback,
  isProcessingHermesRevision,
  isUpdatingWriteback,
  isGeneratingReference,
  isGeneratingProviderReference,
  isUpdatingReference,
  chapterError,
  sceneError,
  manuscriptError,
  manuscriptStatus,
  writebackError,
  writebackStatus,
  referenceError,
  referenceStatus,
  manuscriptEditTitle,
  manuscriptEditContent,
  sceneDraft,
  chapterDraft,
  referenceDraft,
  compileResult,
  revisionDiff,
  manuscriptExport,
  activeProposal,
  activeWritebackProposal,
  activeReferenceSuggestion,
  pendingProposalCount,
  pendingWritebackCount,
  pendingReferenceCount,
  acceptedSceneCount,
  revisionCount,
  unassignedSceneContracts,
  sceneStateLabel,
  chapterStateLabel
} = storeToRefs(store)
const {
  loadManuscriptScenes,
  loadManuscriptRevisions,
  loadWritebackProposals,
  loadReferenceSuggestions,
  startNewChapter,
  startNewSceneContract,
  saveChapter,
  deleteChapter,
  saveSceneContract,
  deleteSceneContract,
  compileSceneContract,
  createProposalFromScene,
  updateProposalStatus,
  generateReferenceSuggestion,
  updateReferenceStatus,
  loadRevisionDiff,
  restoreRevision,
  exportManuscript,
  startEditingManuscriptScene,
  cancelEditingManuscriptScene,
  saveManuscriptSceneEdit,
  createWritebackFromRevision,
  processRevisionWithHermes,
  updateWritebackStatus,
  scenesForChapter,
  chapterTitleForScene,
  referenceWarnings,
  revisionLabel,
  statusText,
  formatJson
} = store
</script>

<template>
<section class="manuscript-workspace">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Chapters / Scene Contracts</p>
            <h3>Manuscript Inputs</h3>
          </div>
          <div class="button-row">
            <button class="secondary" type="button" @click="startNewChapter">
              New Chapter
            </button>
            <button class="primary" type="button" @click="startNewSceneContract">
              New Scene
            </button>
          </div>
        </div>

        <div class="chapter-grid">
          <aside class="chapter-list" aria-label="Manuscript chapters">
            <button
              v-for="chapter in manuscriptChapters"
              :key="chapter.id"
              :class="{ active: chapter.id === activeChapterId }"
              type="button"
              @click="activeChapterId = chapter.id"
            >
              <span>Chapter {{ chapter.sequence }}: {{ chapter.title }}</span>
              <small>{{ scenesForChapter(chapter.id).length }} scenes</small>
            </button>
            <p v-if="manuscriptChapters.length === 0" class="empty-state">
              No chapters yet.
            </p>
          </aside>

          <form class="chapter-editor" @submit.prevent="saveChapter">
            <div class="scene-fields">
              <label>
                <span>Chapter No.</span>
                <input v-model.number="chapterDraft.sequence" type="number" min="1" max="999" />
              </label>
              <label>
                <span>Title</span>
                <input v-model="chapterDraft.title" autocomplete="off" placeholder="The locked map" />
              </label>
            </div>
            <label>
              <span>Summary</span>
              <textarea
                v-model="chapterDraft.summary"
                rows="3"
                placeholder="What this chapter changes in the manuscript."
              />
            </label>
            <div class="form-actions artifact-actions">
              <p v-if="chapterError" class="error">{{ chapterError }}</p>
              <p v-else class="save-state">{{ chapterStateLabel }}</p>
              <div class="button-row">
                <button
                  v-if="activeChapterId"
                  class="secondary danger"
                  type="button"
                  :disabled="isDeletingChapter"
                  @click="deleteChapter"
                >
                  {{ isDeletingChapter ? 'Deleting...' : 'Delete Chapter' }}
                </button>
                <button class="primary" type="submit" :disabled="isSavingChapter">
                  {{ isSavingChapter ? 'Saving...' : activeChapterId ? 'Save Chapter' : 'Create Chapter' }}
                </button>
              </div>
            </div>
          </form>
        </div>

        <div class="scene-grid">
          <aside class="scene-list" aria-label="Scene contracts">
            <template v-for="chapter in manuscriptChapters" :key="chapter.id">
              <p class="list-heading">Chapter {{ chapter.sequence }}</p>
              <button
                v-for="scene in scenesForChapter(chapter.id)"
                :key="scene.id"
                :class="{ active: scene.id === activeSceneId }"
                type="button"
                @click="activeSceneId = scene.id"
              >
                <span>{{ scene.sequence }}. {{ scene.title }}</span>
                <small>{{ scene.pov || 'No POV' }}</small>
              </button>
            </template>
            <template v-if="unassignedSceneContracts.length">
              <p class="list-heading">Unassigned</p>
              <button
                v-for="scene in unassignedSceneContracts"
                :key="scene.id"
                :class="{ active: scene.id === activeSceneId }"
                type="button"
                @click="activeSceneId = scene.id"
              >
                <span>{{ scene.sequence }}. {{ scene.title }}</span>
                <small>{{ scene.pov || 'No POV' }}</small>
              </button>
            </template>
            <p v-if="sceneContracts.length === 0" class="empty-state">
              No Scene contracts yet.
            </p>
          </aside>

          <form class="scene-editor" @submit.prevent="saveSceneContract">
            <div class="scene-fields">
              <label>
                <span>Chapter</span>
                <select v-model="sceneDraft.chapter_id">
                  <option value="">Unassigned</option>
                  <option
                    v-for="chapter in manuscriptChapters"
                    :key="chapter.id"
                    :value="chapter.id"
                  >
                    Chapter {{ chapter.sequence }}: {{ chapter.title }}
                  </option>
                </select>
              </label>
              <label>
                <span>Sequence</span>
                <input v-model.number="sceneDraft.sequence" type="number" min="1" max="999" />
              </label>
              <label>
                <span>Title</span>
                <input v-model="sceneDraft.title" autocomplete="off" placeholder="The map changes" />
              </label>
              <label>
                <span>POV</span>
                <input v-model="sceneDraft.pov" autocomplete="off" placeholder="Lin Ye" />
              </label>
              <label>
                <span>Source Step</span>
                <input
                  v-model.number="sceneDraft.source_artifact_step"
                  type="number"
                  min="1"
                  max="10"
                />
              </label>
            </div>

            <label>
              <span>Goal</span>
              <textarea v-model="sceneDraft.goal" rows="3" placeholder="What the POV wants." />
            </label>
            <label>
              <span>Conflict</span>
              <textarea
                v-model="sceneDraft.conflict"
                rows="3"
                placeholder="What blocks the goal."
              />
            </label>
            <label>
              <span>Turning Point</span>
              <textarea
                v-model="sceneDraft.turning_point"
                rows="3"
                placeholder="What changes by the end."
              />
            </label>
            <label>
              <span>Required Canon</span>
              <textarea
                v-model="sceneDraft.required_canon"
                rows="4"
                placeholder="Facts this scene must respect."
              />
            </label>
            <label>
              <span>Forbidden Facts</span>
              <textarea
                v-model="sceneDraft.forbidden_facts"
                rows="4"
                placeholder="Facts this scene cannot reveal or contradict."
              />
            </label>
            <label>
              <span>Open Threads</span>
              <textarea
                v-model="sceneDraft.open_threads"
                rows="4"
                placeholder="Questions advanced or opened by this scene."
              />
            </label>

            <div class="form-actions artifact-actions">
              <p v-if="sceneError" class="error">{{ sceneError }}</p>
              <p v-else class="save-state">{{ sceneStateLabel }}</p>
              <div class="button-row">
                <button
                  v-if="activeSceneId"
                  class="secondary danger"
                  type="button"
                  :disabled="isDeletingScene"
                  @click="deleteSceneContract"
                >
                  {{ isDeletingScene ? 'Deleting...' : 'Delete' }}
                </button>
                <button
                  v-if="activeSceneId"
                  class="secondary"
                  type="button"
                  :disabled="isCompilingScene"
                  @click="compileSceneContract"
                >
                  {{ isCompilingScene ? 'Compiling...' : 'Compile' }}
                </button>
                <button
                  v-if="activeSceneId"
                  class="secondary"
                  type="button"
                  :disabled="isCreatingProposal"
                  @click="createProposalFromScene()"
                >
                  {{ isCreatingProposal ? 'Creating...' : 'Create Proposal' }}
                </button>
                <button
                  v-if="activeSceneId"
                  class="secondary"
                  type="button"
                  :disabled="isCreatingProviderProposal"
                  @click="createProposalFromScene(true)"
                >
                  {{ isCreatingProviderProposal ? 'Creating...' : 'Provider Proposal' }}
                </button>
                <button class="primary" type="submit" :disabled="isSavingScene">
                  {{ isSavingScene ? 'Saving...' : activeSceneId ? 'Save Scene' : 'Create Scene' }}
                </button>
              </div>
            </div>
          </form>
        </div>

        <div v-if="compileResult" class="compile-output">
          <section>
            <p class="eyebrow">Context Package</p>
            <pre>{{ compileResult.context }}</pre>
          </section>
          <section>
            <p class="eyebrow">Draft Placeholder</p>
            <pre>{{ compileResult.draft }}</pre>
          </section>
          <section>
            <p class="eyebrow">Checklist</p>
            <ul>
              <li v-for="item in compileResult.checklist" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>

        <section class="reference-workspace">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Structured Copilot</p>
              <h3>Reference Suggestions</h3>
            </div>
            <div class="button-row">
              <span class="step-chip">{{ pendingReferenceCount }} pending</span>
              <button class="secondary" type="button" @click="loadReferenceSuggestions()">
                Refresh
              </button>
            </div>
          </div>

          <form class="reference-form" @submit.prevent="generateReferenceSuggestion(false)">
            <div class="scene-fields">
              <label>
                <span>Request</span>
                <select v-model="referenceDraft.suggestion_type">
                  <option value="brainstorm">Brainstorm</option>
                  <option value="scene_bridge">Scene bridge</option>
                  <option value="conflict_options">Conflict options</option>
                  <option value="character_motivation">Character motivation</option>
                  <option value="canon_gap">Canon gap</option>
                  <option value="prose_reference">Prose reference</option>
                  <option value="structure_fix">Structure fix</option>
                </select>
              </label>
              <label>
                <span>Scope</span>
                <select v-model="referenceDraft.scope_type">
                  <option value="project">Project</option>
                  <option value="snowflake_step">Snowflake step</option>
                  <option value="scene">Scene</option>
                  <option value="canon_entity">Canon entity</option>
                  <option value="memory_record">Memory record</option>
                  <option value="manuscript_scene">Manuscript scene</option>
                  <option value="graph">Graph</option>
                </select>
              </label>
              <label>
                <span>Scope Ref</span>
                <input
                  v-model="referenceDraft.scope_ref"
                  autocomplete="off"
                  placeholder="Scene id, step number, or leave blank"
                />
              </label>
            </div>

            <label>
              <span>Writing Problem</span>
              <textarea
                v-model="referenceDraft.author_problem"
                rows="3"
                placeholder="What is blocked, unclear, or structurally weak?"
              />
            </label>
            <label>
              <span>Desired Output</span>
              <input
                v-model="referenceDraft.desired_output"
                autocomplete="off"
                placeholder="Three options, one bridge, motivation notes..."
              />
            </label>

            <div class="form-actions artifact-actions">
              <p v-if="referenceError" class="error">{{ referenceError }}</p>
              <p v-else-if="referenceStatus" class="save-state">{{ referenceStatus }}</p>
              <p v-else class="save-state">Reference suggestions are advisory and reviewable.</p>
              <div class="button-row">
                <button
                  class="secondary"
                  type="button"
                  :disabled="isGeneratingProviderReference"
                  @click="generateReferenceSuggestion(true)"
                >
                  {{ isGeneratingProviderReference ? 'Generating...' : 'Provider Reference' }}
                </button>
                <button class="primary" type="submit" :disabled="isGeneratingReference">
                  {{ isGeneratingReference ? 'Generating...' : 'Generate Reference' }}
                </button>
              </div>
            </div>
          </form>

          <div class="proposal-grid">
            <aside class="proposal-list" aria-label="Reference suggestions">
              <button
                v-for="suggestion in referenceSuggestions"
                :key="suggestion.id"
                :class="{ active: suggestion.id === activeReferenceId }"
                type="button"
                @click="activeReferenceId = suggestion.id"
              >
                <span>{{ suggestion.title }}</span>
                <small>{{ suggestion.suggestion_type.replace('_', ' ') }} / {{ statusText(suggestion.status) }}</small>
              </button>
              <p v-if="referenceSuggestions.length === 0" class="empty-state">
                No reference suggestions yet.
              </p>
            </aside>

            <section v-if="activeReferenceSuggestion" class="proposal-detail">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">{{ statusText(activeReferenceSuggestion.status) }}</p>
                  <h4>{{ activeReferenceSuggestion.title }}</h4>
                </div>
                <div class="button-row">
                  <button
                    v-if="activeReferenceSuggestion.status === 'pending_review'"
                    class="secondary danger"
                    type="button"
                    :disabled="isUpdatingReference"
                    @click="updateReferenceStatus(activeReferenceSuggestion.id, 'rejected')"
                  >
                    Reject
                  </button>
                  <button
                    v-if="activeReferenceSuggestion.status === 'pending_review'"
                    class="primary"
                    type="button"
                    :disabled="isUpdatingReference"
                    @click="updateReferenceStatus(activeReferenceSuggestion.id, 'accepted')"
                  >
                    Accept Reference
                  </button>
                </div>
              </div>

              <section>
                <p class="eyebrow">Suggestion</p>
                <pre>{{ activeReferenceSuggestion.content }}</pre>
              </section>
              <section>
                <p class="eyebrow">Rationale</p>
                <p class="proposal-rationale">{{ activeReferenceSuggestion.rationale }}</p>
              </section>
              <section v-if="referenceWarnings(activeReferenceSuggestion).length">
                <p class="eyebrow">Warnings and Notes</p>
                <ul>
                  <li
                    v-for="item in referenceWarnings(activeReferenceSuggestion)"
                    :key="item"
                  >
                    {{ item }}
                  </li>
                </ul>
              </section>
              <section>
                <p class="eyebrow">Used Context</p>
                <pre>{{ activeReferenceSuggestion.used_context }}</pre>
              </section>
            </section>
          </div>
        </section>

        <section class="proposal-workspace">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Review Queue</p>
              <h3>Manuscript Proposals</h3>
            </div>
            <div class="button-row">
              <span class="step-chip">{{ pendingProposalCount }} pending</span>
              <span class="step-chip">{{ acceptedSceneCount }} accepted scenes</span>
              <span class="step-chip">{{ revisionCount }} revisions</span>
              <span class="step-chip">{{ pendingWritebackCount }} write-backs</span>
            </div>
          </div>

          <p v-if="manuscriptError" class="error">{{ manuscriptError }}</p>
          <p v-else-if="manuscriptStatus" class="save-state">{{ manuscriptStatus }}</p>

          <div class="proposal-grid">
            <aside class="proposal-list" aria-label="Manuscript proposals">
              <button
                v-for="proposal in manuscriptProposals"
                :key="proposal.id"
                :class="{ active: proposal.id === activeProposalId }"
                type="button"
                @click="activeProposalId = proposal.id"
              >
                <span>{{ proposal.title }}</span>
                <small>{{ statusText(proposal.status) }}</small>
              </button>
              <p v-if="manuscriptProposals.length === 0" class="empty-state">
                No manuscript proposals yet.
              </p>
            </aside>

            <section v-if="activeProposal" class="proposal-detail">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">{{ statusText(activeProposal.status) }}</p>
                  <h4>{{ activeProposal.title }}</h4>
                </div>
                <div class="button-row">
                  <button
                    v-if="activeProposal.status === 'pending_review'"
                    class="secondary danger"
                    type="button"
                    :disabled="isUpdatingProposal"
                    @click="updateProposalStatus(activeProposal.id, 'rejected')"
                  >
                    Reject
                  </button>
                  <button
                    v-if="activeProposal.status === 'pending_review'"
                    class="primary"
                    type="button"
                    :disabled="isUpdatingProposal"
                    @click="updateProposalStatus(activeProposal.id, 'accepted')"
                  >
                    Accept
                  </button>
                </div>
              </div>

              <section>
                <p class="eyebrow">Proposed Draft</p>
                <pre>{{ activeProposal.content }}</pre>
              </section>
              <section>
                <p class="eyebrow">Review Checklist</p>
                <ul>
                  <li v-for="item in activeProposal.checklist" :key="item">{{ item }}</li>
                </ul>
              </section>
              <section>
                <p class="eyebrow">Source Context</p>
                <pre>{{ activeProposal.context }}</pre>
              </section>
            </section>
          </div>
        </section>

        <section class="accepted-manuscript">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Accepted Manuscript</p>
              <h3>Current Scene Drafts</h3>
            </div>
            <div class="button-row">
              <button
                class="secondary"
                type="button"
                :disabled="isExportingManuscript"
                @click="exportManuscript"
              >
                {{ isExportingManuscript ? 'Exporting...' : 'Export Markdown' }}
              </button>
              <button class="secondary" type="button" @click="loadManuscriptScenes()">
                Refresh
              </button>
            </div>
          </div>

          <section v-if="manuscriptExport" class="export-output">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">{{ manuscriptExport.scene_count }} scenes</p>
                <h4>{{ manuscriptExport.title }}</h4>
              </div>
              <small>{{ manuscriptExport.generated_at }}</small>
            </div>
            <pre>{{ manuscriptExport.content }}</pre>
          </section>

          <div class="accepted-list">
            <article v-for="scene in manuscriptScenes" :key="scene.id" class="accepted-item">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">{{ chapterTitleForScene(scene.scene_id) }} / Version {{ scene.version }}</p>
                  <h4>{{ scene.title }}</h4>
                </div>
                <div class="revision-actions">
                  <small>{{ scene.accepted_at }}</small>
                  <div class="button-row">
                    <button
                      v-if="editingManuscriptSceneId !== scene.scene_id"
                      class="secondary"
                      type="button"
                      @click="startEditingManuscriptScene(scene)"
                    >
                      Edit
                    </button>
                  </div>
                </div>
              </div>
              <form
                v-if="editingManuscriptSceneId === scene.scene_id"
                class="manuscript-edit"
                @submit.prevent="saveManuscriptSceneEdit(scene.scene_id)"
              >
                <label>
                  <span>Title</span>
                  <input v-model="manuscriptEditTitle" autocomplete="off" />
                </label>
                <label>
                  <span>Content</span>
                  <textarea v-model="manuscriptEditContent" rows="14" />
                </label>
                <div class="form-actions artifact-actions">
                  <p class="save-state">Saving creates a new manuscript revision.</p>
                  <div class="button-row">
                    <button class="secondary" type="button" @click="cancelEditingManuscriptScene">
                      Cancel
                    </button>
                    <button class="primary" type="submit" :disabled="isSavingManuscriptScene">
                      {{ isSavingManuscriptScene ? 'Saving...' : 'Save Version' }}
                    </button>
                  </div>
                </div>
              </form>
              <pre v-else>{{ scene.content }}</pre>
            </article>
            <p v-if="manuscriptScenes.length === 0" class="empty-state">
              No accepted manuscript scenes yet.
            </p>
          </div>
        </section>

        <section class="revision-history">
          <div class="panel-header">
            <div>
              <p class="eyebrow">Version History</p>
              <h3>Accepted Revisions</h3>
            </div>
            <button class="secondary" type="button" @click="loadManuscriptRevisions()">
              Refresh
            </button>
          </div>

          <div v-if="manuscriptRevisions.length" class="revision-tools">
            <label>
              <span>Base Revision</span>
              <select v-model="diffLeftRevisionId">
                <option
                  v-for="revision in manuscriptRevisions"
                  :key="`left-${revision.id}`"
                  :value="revision.id"
                >
                  {{ revisionLabel(revision) }}
                </option>
              </select>
            </label>
            <label>
              <span>Compare Revision</span>
              <select v-model="diffRightRevisionId">
                <option
                  v-for="revision in manuscriptRevisions"
                  :key="`right-${revision.id}`"
                  :value="revision.id"
                >
                  {{ revisionLabel(revision) }}
                </option>
              </select>
            </label>
            <button class="secondary" type="button" :disabled="isLoadingDiff" @click="loadRevisionDiff">
              {{ isLoadingDiff ? 'Loading...' : 'Compare' }}
            </button>
          </div>

          <section v-if="revisionDiff" class="diff-output">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">Revision Diff</p>
                <h4>{{ revisionDiff.left_title }} -> {{ revisionDiff.right_title }}</h4>
              </div>
              <span class="step-chip">{{ revisionDiff.diff_lines.length }} lines</span>
            </div>
            <pre>{{ revisionDiff.diff_lines.join('\n') }}</pre>
          </section>

          <div class="revision-list">
            <article v-for="revision in manuscriptRevisions" :key="revision.id" class="revision-item">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">Version {{ revision.version }}</p>
                  <h4>{{ revision.title }}</h4>
                </div>
                <div class="revision-actions">
                  <small>{{ revision.created_at }}</small>
                  <div class="button-row">
                    <button
                      class="secondary"
                      type="button"
                      :disabled="isProcessingHermesRevision"
                      @click="processRevisionWithHermes(revision.id)"
                    >
                      {{ isProcessingHermesRevision ? 'Processing...' : 'Process with Hermes' }}
                    </button>
                    <button
                      class="secondary"
                      type="button"
                      :disabled="isCreatingWriteback"
                      @click="createWritebackFromRevision(revision.id)"
                    >
                      Local Suggest
                    </button>
                    <button
                      class="secondary"
                      type="button"
                      :disabled="isCreatingProviderWriteback"
                      @click="createWritebackFromRevision(revision.id, true)"
                    >
                      Provider Suggest
                    </button>
                    <button
                      class="secondary danger"
                      type="button"
                      :disabled="isRestoringRevision"
                      @click="restoreRevision(revision.id)"
                    >
                      Restore
                    </button>
                  </div>
                </div>
              </div>
              <pre>{{ revision.content }}</pre>
            </article>
            <p v-if="manuscriptRevisions.length === 0" class="empty-state">
              No accepted revisions yet.
            </p>
          </div>
        </section>

        <section class="writeback-review">
          <div class="panel-header">
            <div>
              <p class="eyebrow">State Write-back</p>
              <h3>Canon / Memory Proposals</h3>
            </div>
            <div class="button-row">
              <span class="step-chip">{{ pendingWritebackCount }} pending</span>
              <button class="secondary" type="button" @click="loadWritebackProposals()">
                Refresh
              </button>
            </div>
          </div>

          <p v-if="writebackError" class="error">{{ writebackError }}</p>
          <p v-else-if="writebackStatus" class="save-state">{{ writebackStatus }}</p>

          <section v-if="hermesProcessReport" class="export-output">
            <div class="panel-header compact">
              <div>
                <p class="eyebrow">Hermes {{ hermesProcessReport.status }}</p>
                <h4>{{ hermesProcessReport.processed_source_ref }}</h4>
              </div>
              <span class="step-chip">{{ hermesProcessReport.wiki_changes.length }} wiki changes</span>
            </div>
            <p class="proposal-rationale">{{ hermesProcessReport.summary }}</p>
            <dl v-if="hermesProcessReport.wiki_changes.length" class="proposal-meta">
              <div v-for="change in hermesProcessReport.wiki_changes" :key="`${change.action}-${change.path}`">
                <dt>{{ change.action }}</dt>
                <dd>{{ change.path }} - {{ change.reason }}</dd>
              </div>
            </dl>
            <dl v-if="hermesProcessReport.issues.length" class="proposal-meta">
              <div v-for="issue in hermesProcessReport.issues" :key="`${issue.code}-${issue.message}`">
                <dt>{{ issue.severity }} / {{ issue.code }}</dt>
                <dd>{{ issue.message }}</dd>
              </div>
            </dl>
          </section>

          <div class="proposal-grid">
            <aside class="proposal-list" aria-label="Write-back proposals">
              <button
                v-for="proposal in writebackProposals"
                :key="proposal.id"
                :class="{ active: proposal.id === activeWritebackId }"
                type="button"
                @click="activeWritebackId = proposal.id"
              >
                <span>{{ proposal.title }}</span>
                <small>{{ proposal.target.replace('_', ' ') }} / {{ statusText(proposal.status) }}</small>
              </button>
              <p v-if="writebackProposals.length === 0" class="empty-state">
                No write-back proposals yet.
              </p>
            </aside>

            <section v-if="activeWritebackProposal" class="proposal-detail">
              <div class="panel-header compact">
                <div>
                  <p class="eyebrow">{{ statusText(activeWritebackProposal.status) }}</p>
                  <h4>{{ activeWritebackProposal.title }}</h4>
                </div>
                <div class="button-row">
                  <button
                    v-if="activeWritebackProposal.status === 'pending_review'"
                    class="secondary danger"
                    type="button"
                    :disabled="isUpdatingWriteback"
                    @click="updateWritebackStatus(activeWritebackProposal.id, 'rejected')"
                  >
                    Reject
                  </button>
                  <button
                    v-if="activeWritebackProposal.status === 'pending_review'"
                    class="primary"
                    type="button"
                    :disabled="isUpdatingWriteback"
                    @click="updateWritebackStatus(activeWritebackProposal.id, 'accepted')"
                  >
                    Accept
                  </button>
                </div>
              </div>

              <dl class="proposal-meta">
                <div>
                  <dt>Target</dt>
                  <dd>{{ activeWritebackProposal.target.replace('_', ' ') }}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{{ activeWritebackProposal.source_ref || 'none' }}</dd>
                </div>
                <div>
                  <dt>Applied Record</dt>
                  <dd>{{ activeWritebackProposal.applied_record_id || 'not applied' }}</dd>
                </div>
              </dl>

              <section>
                <p class="eyebrow">Rationale</p>
                <p class="proposal-rationale">{{ activeWritebackProposal.rationale || 'No rationale recorded.' }}</p>
              </section>
              <section>
                <p class="eyebrow">Structured Payload</p>
                <pre>{{ formatJson(activeWritebackProposal.payload) }}</pre>
              </section>
            </section>
          </div>
        </section>
      </section>
    
</template>
