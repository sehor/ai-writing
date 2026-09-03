<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useManuscriptStore } from '../../stores/manuscript'

const store = useManuscriptStore()
const {
  sceneContracts,
  manuscriptChapters,
  activeChapterId,
  activeSceneId,
  isSavingScene,
  isDeletingScene,
  isSavingChapter,
  isDeletingChapter,
  isCompilingScene,
  isCreatingProposal,
  isCreatingProviderProposal,
  chapterError,
  sceneError,
  sceneDraft,
  chapterDraft,
  compileResult,
  unassignedSceneContracts,
  sceneStateLabel,
  chapterStateLabel,
} = storeToRefs(store)
const {
  startNewChapter,
  startNewSceneContract,
  saveChapter,
  deleteChapter,
  saveSceneContract,
  deleteSceneContract,
  compileSceneContract,
  createProposalFromScene,
  scenesForChapter,
} = store
</script>

<template>
  <div class="panel-header">
    <div>
      <p class="eyebrow">Chapters / Scene Contracts</p>
      <h3>Manuscript Inputs</h3>
    </div>
    <div class="button-row">
      <button class="secondary" type="button" @click="startNewChapter">New Chapter</button>
      <button class="primary" type="button" @click="startNewSceneContract">New Scene</button>
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
      <p v-if="manuscriptChapters.length === 0" class="empty-state">No chapters yet.</p>
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
      <p v-if="sceneContracts.length === 0" class="empty-state">No Scene contracts yet.</p>
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
        <span>Outcome / Disaster</span>
        <textarea
          v-model="sceneDraft.outcome"
          rows="3"
          placeholder="What concrete result leaves the scene changed."
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
        <span>Information Delta</span>
        <textarea
          v-model="sceneDraft.information_delta"
          rows="3"
          placeholder="What the reader or characters learn, lose, or misunderstand."
        />
      </label>
      <label>
        <span>Character State Delta</span>
        <textarea
          v-model="sceneDraft.character_state_delta"
          rows="3"
          placeholder="How goals, relationships, resources, or emotions change."
        />
      </label>
      <label>
        <span>StoryThread Actions</span>
        <textarea
          v-model="sceneDraft.story_thread_actions"
          rows="3"
          placeholder="Thread ID and action, one per line."
        />
      </label>
      <label>
        <span>Legacy open-thread notes</span>
        <textarea
          v-model="sceneDraft.open_threads"
          rows="4"
          placeholder="Compatibility only; use structured StoryThread actions for generation."
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
</template>
