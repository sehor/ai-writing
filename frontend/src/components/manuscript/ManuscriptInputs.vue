<script setup lang="ts">
import { useWorkspaceStore } from '../../stores/workspace'
import { storeToRefs } from 'pinia'
import { useManuscriptStore } from '../../stores/manuscript'

const workspace = useWorkspaceStore()
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
<label class="generation-model-picker">生成模型<select v-model="workspace.selectedModelProfile" aria-label="生成模型"><option value="">自动选择 / 本地模式</option><option v-for="profile in workspace.modelProfiles" :key="profile.id" :value="profile.id">{{ profile.label }}{{ profile.configured ? '' : '（未配置）' }}</option></select></label>
  <div class="panel-header">
    <div>
      <h3>章节与场景</h3>
    </div>
    <div class="button-row">
      <button class="secondary" type="button" @click="startNewChapter">新建章节</button>
      <button class="primary" type="button" @click="startNewSceneContract">新建场景</button>
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
        <span>第 {{ chapter.sequence }} 章： {{ chapter.title }}</span>
        <small>{{ scenesForChapter(chapter.id).length }} 个场景</small>
      </button>
      <p v-if="manuscriptChapters.length === 0" class="empty-state">还没有章节。先建立故事目录。</p>
    </aside>

    <form class="chapter-editor" @submit.prevent="saveChapter">
      <div class="scene-fields">
        <label>
          <span>章节序号</span>
          <input v-model.number="chapterDraft.sequence" type="number" min="1" max="999" />
        </label>
        <label>
          <span>标题</span>
          <input v-model="chapterDraft.title" autocomplete="off" placeholder="被锁住的地图" />
        </label>
      </div>
      <label>
        <span>摘要</span>
        <textarea
          v-model="chapterDraft.summary"
          rows="3"
          placeholder="这一章推动了怎样的变化？"
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
            {{ isDeletingChapter ? '删除中…' : '删除章节' }}
          </button>
          <button class="primary" type="submit" :disabled="isSavingChapter">
            {{ isSavingChapter ? '保存中…' : activeChapterId ? '保存章节' : '创建章节' }}
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
          <small>{{ scene.pov || '未指定视角' }}</small>
        </button>
      </template>
      <template v-if="unassignedSceneContracts.length">
        <p class="list-heading">未分章</p>
        <button
          v-for="scene in unassignedSceneContracts"
          :key="scene.id"
          :class="{ active: scene.id === activeSceneId }"
          type="button"
          @click="activeSceneId = scene.id"
        >
          <span>{{ scene.sequence }}. {{ scene.title }}</span>
          <small>{{ scene.pov || '未指定视角' }}</small>
        </button>
      </template>
      <p v-if="sceneContracts.length === 0" class="empty-state">还没有场景。先创建一个场景契约。</p>
    </aside>

    <form class="scene-editor" @submit.prevent="saveSceneContract">
      <div class="scene-fields">
        <label>
          <span>章节</span>
          <select v-model="sceneDraft.chapter_id">
            <option value="">未分章</option>
            <option
              v-for="chapter in manuscriptChapters"
              :key="chapter.id"
              :value="chapter.id"
            >
              第 {{ chapter.sequence }} 章： {{ chapter.title }}
            </option>
          </select>
        </label>
        <label>
          <span>顺序</span>
          <input v-model.number="sceneDraft.sequence" type="number" min="1" max="999" />
        </label>
        <label>
          <span>标题</span>
          <input v-model="sceneDraft.title" autocomplete="off" placeholder="地图发生变化" />
        </label>
        <label>
          <span>叙述视角</span>
          <input v-model="sceneDraft.pov" autocomplete="off" placeholder="林野" />
        </label>
        <label>
          <span>来源步骤</span>
          <input
            v-model.number="sceneDraft.source_artifact_step"
            type="number"
            min="1"
            max="10"
          />
        </label>
      </div>

      <label>
        <span>目标</span>
        <textarea v-model="sceneDraft.goal" rows="3" placeholder="视角人物想实现什么？" />
      </label>
      <label>
        <span>冲突</span>
        <textarea
          v-model="sceneDraft.conflict"
          rows="3"
          placeholder="什么阻碍了目标？"
        />
      </label>
      <label>
        <span>转折点</span>
        <textarea
          v-model="sceneDraft.turning_point"
          rows="3"
          placeholder="场景结束时发生怎样的转折？"
        />
      </label>
      <label>
        <span>结果与转折</span>
        <textarea
          v-model="sceneDraft.outcome"
          rows="3"
          placeholder="这个场景带来什么明确结果？"
        />
      </label>
      <label>
        <span>必需的设定</span>
        <textarea
          v-model="sceneDraft.required_canon"
          rows="4"
          placeholder="这个场景必须遵守的设定。"
        />
      </label>
      <label>
        <span>禁止出现的事实</span>
        <textarea
          v-model="sceneDraft.forbidden_facts"
          rows="4"
          placeholder="不应揭露或违背的事实。"
        />
      </label>
      <label>
        <span>信息变化</span>
        <textarea
          v-model="sceneDraft.information_delta"
          rows="3"
          placeholder="读者或人物获知、失去或误解了什么？"
        />
      </label>
      <label>
        <span>人物状态变化</span>
        <textarea
          v-model="sceneDraft.character_state_delta"
          rows="3"
          placeholder="目标、关系、资源或情绪发生怎样的变化？"
        />
      </label>
      <label>
        <span>故事线操作</span>
        <textarea
          v-model="sceneDraft.story_thread_actions"
          rows="3"
          placeholder="每行填写一个故事线标识与操作。"
        />
      </label>
      <label>
        <span>旧版未完结线索</span>
        <textarea
          v-model="sceneDraft.open_threads"
          rows="4"
          placeholder="旧版兼容备注；生成时请使用结构化故事线操作。"
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
            {{ isDeletingScene ? '删除中…' : '删除' }}
          </button>
          <button
            v-if="activeSceneId"
            class="secondary"
            type="button"
            :disabled="isCompilingScene"
            @click="compileSceneContract"
          >
            {{ isCompilingScene ? '编译中…' : '编译场景' }}
          </button>
          <button
            v-if="activeSceneId"
            class="secondary"
            type="button"
            :disabled="isCreatingProposal"
            @click="createProposalFromScene()"
          >
            {{ isCreatingProposal ? '创建中…' : '创建草稿' }}
          </button>
          <button
            v-if="activeSceneId"
            class="secondary"
            type="button"
            :disabled="isCreatingProviderProposal"
            @click="createProposalFromScene(true)"
          >
            {{ isCreatingProviderProposal ? '创建中…' : '使用模型生成草稿' }}
          </button>
          <button class="primary" type="submit" :disabled="isSavingScene">
            {{ isSavingScene ? '保存中…' : activeSceneId ? '保存场景' : '创建场景' }}
          </button>
        </div>
      </div>
    </form>
  </div>

  <div v-if="compileResult" class="compile-output">
    <section>
      <p class="eyebrow">上下文资料</p>
      <pre>{{ compileResult.context }}</pre>
    </section>
    <section>
      <p class="eyebrow">本地示例草稿</p>
      <pre>{{ compileResult.draft }}</pre>
    </section>
    <section>
      <p class="eyebrow">检查清单</p>
      <ul>
        <li v-for="item in compileResult.checklist" :key="item">{{ item }}</li>
      </ul>
    </section>
  </div>
</template>
