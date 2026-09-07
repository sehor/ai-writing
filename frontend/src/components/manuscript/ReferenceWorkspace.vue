<script setup lang="ts">
import { watch } from 'vue'
import { storeToRefs } from 'pinia'
import { statusText } from '../../utils/format'
import { useReviewsStore } from '../../stores/reviews'
import { useCopilotContextStore } from '../../stores/copilotContext'
import { useReferenceApplicationStore } from '../../stores/referenceApplication'

const store = useReviewsStore()
const copilot = useCopilotContextStore()
const application = useReferenceApplicationStore()
const {
  referenceSuggestions,
  activeReferenceId,
  isGeneratingReference,
  isGeneratingProviderReference,
  isUpdatingReference,
  referenceError,
  referenceStatus,
  referenceDraft,
  activeReferenceSuggestion,
  pendingReferenceCount,
} = storeToRefs(store)
const {
  loadReferenceSuggestions,
  generateReferenceSuggestion,
  updateReferenceStatus,
  referenceWarnings
} = store
const {
  applicationText,
  mode,
  previewText,
  error: applicationError,
  status: applicationStatus,
  canUndo,
} = storeToRefs(application)
const { selectSuggestion, previewSuggestion, applySuggestion, undo } = application
watch(activeReferenceSuggestion, (suggestion) => selectSuggestion(suggestion ?? null), { immediate: true })
</script>

<template>
  <section class="reference-workspace">
    <div class="panel-header">
      <div>
        <h3>参考建议</h3>
      </div>
      <div class="button-row">
        <span class="step-chip">{{ pendingReferenceCount }} 待审</span>
        <button class="secondary" type="button" @click="loadReferenceSuggestions()">刷新</button>
      </div>
    </div>

    <form class="reference-form" @submit.prevent="generateReferenceSuggestion(false)">
      <section v-if="copilot.request" aria-label="求助原文" class="draft-conflict">
        <p>{{ copilot.request.selection_mode === 'selection' ? '选中文字' : '整场景草稿' }} · {{ copilot.request.source_kind === 'proposal_draft' ? '待审核草稿' : '正文编辑草稿' }} · 基于 v{{ copilot.request.expected_scene_version }}</p>
        <details><summary>查看求助原文</summary><pre>{{ copilot.request.selected_text }}</pre></details>
        <p v-if="copilot.stale" class="error-text" role="alert">原文、目标或版本已变化，请回到编辑器重新选择。</p>
        <button type="button" class="quiet-button" @click="copilot.clear()">移除选区，使用普通参考请求</button>
      </section>
      <div class="scene-fields">
        <label>
          <span>请求类型</span>
          <select v-model="referenceDraft.suggestion_type">
            <option value="brainstorm">构思灵感</option>
            <option value="scene_bridge">场景衔接</option>
            <option value="conflict_options">冲突处理</option>
            <option value="character_motivation">人物动机</option>
            <option value="canon_gap">设定缺口</option>
            <option value="prose_reference">写作参考</option>
            <option value="structure_fix">结构调整</option>
          </select>
        </label>
        <label>
          <span>范围</span>
          <select v-model="referenceDraft.scope_type" :disabled="!!copilot.request">
            <option value="project">项目</option>
            <option value="snowflake_step">雪花步骤</option>
            <option value="scene">场景</option>
            <option value="canon_entity">设定条目</option>
            <option value="memory_record">记忆记录</option>
            <option value="manuscript_scene">正文场景</option>
            <option value="graph">结构分析</option>
          </select>
        </label>
        <label>
          <span>范围标识</span>
          <input
            v-model="referenceDraft.scope_ref"
            :disabled="!!copilot.request"
            autocomplete="off"
            placeholder="填写场景标识或步骤序号，也可留空"
          />
        </label>
      </div>

      <label>
        <span>写作问题</span>
        <textarea
          v-model="referenceDraft.author_problem"
          rows="3"
          placeholder="写作卡在哪里，哪些地方需要理清？"
        />
      </label>
      <label>
        <span>期望结果</span>
        <input
          v-model="referenceDraft.desired_output"
          autocomplete="off"
          placeholder="如：三个方案、一段衔接、人物动机说明"
        />
      </label>

      <div class="form-actions artifact-actions">
        <p v-if="referenceError" class="error">{{ referenceError }}</p>
        <p v-else-if="referenceStatus" class="save-state">{{ referenceStatus }}</p>
        <p v-else class="save-state">参考建议仅供创作参考，由你决定是否采用。</p>
        <div class="button-row">
          <button
            class="secondary"
            type="button"
            :disabled="isGeneratingProviderReference || isGeneratingReference || copilot.stale"
            @click="generateReferenceSuggestion(true)"
          >
            {{ isGeneratingProviderReference ? '生成中…' : '使用模型生成参考' }}
          </button>
          <button class="primary" type="submit" :disabled="isGeneratingReference || isGeneratingProviderReference || copilot.stale">
            {{ isGeneratingReference ? '生成中…' : '生成参考建议' }}
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
          <small>{{ statusText(suggestion.suggestion_type) }} / {{ statusText(suggestion.status) }}</small>
        </button>
        <p v-if="referenceSuggestions.length === 0" class="empty-state">
          还没有参考建议。描述你的写作问题以获取建议。
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
              拒绝
            </button>
            <button
              v-if="activeReferenceSuggestion.status === 'pending_review'"
              class="primary"
              type="button"
              :disabled="isUpdatingReference"
              @click="updateReferenceStatus(activeReferenceSuggestion.id, 'accepted')"
            >
              接受参考建议
            </button>
          </div>
        </div>

        <section>
          <p class="eyebrow">建议</p>
          <pre>{{ activeReferenceSuggestion.content }}</pre>
        </section>
        <section v-if="activeReferenceSuggestion.editor_context" class="reference-application">
          <div class="panel-header compact">
            <div>
              <p class="eyebrow">应用到当前草稿</p>
              <p class="save-state">采纳状态只记录评审；应用到草稿是独立操作，不会保存正式版本。</p>
            </div>
            <button
              v-if="canUndo"
              class="secondary"
              type="button"
              data-testid="undo-reference"
              @click="undo"
            >
              撤销上次应用
            </button>
          </div>
          <p class="save-state">
            目标：{{ activeReferenceSuggestion.editor_context.source_kind === 'proposal_draft' ? '待审核草稿' : '正文编辑草稿' }} ·
            场景 {{ activeReferenceSuggestion.editor_context.scene_id }} · 基于 v{{ activeReferenceSuggestion.editor_context.expected_scene_version }}
          </p>
          <label>
            <span>待应用文本</span>
            <textarea
              v-model="applicationText"
              aria-label="待应用文本"
              rows="5"
              maxlength="40000"
              placeholder="从上方建议中摘取或整理一段可直接进入正文的文字"
            />
          </label>
          <label>
            <span>应用方式</span>
            <select v-model="mode" aria-label="应用方式">
              <option value="replace">替换求助原文</option>
              <option value="insert">在求助原文后插入</option>
            </select>
          </label>
          <p v-if="applicationError" class="error-text" role="alert">{{ applicationError }}</p>
          <p v-else-if="applicationStatus" class="save-state">{{ applicationStatus }}</p>
          <div class="button-row">
            <button
              class="secondary"
              type="button"
              data-testid="preview-reference"
              :disabled="!applicationText.trim()"
              @click="previewSuggestion(activeReferenceSuggestion)"
            >
              预览应用
            </button>
            <button
              class="primary"
              type="button"
              data-testid="apply-reference"
              :disabled="!applicationText.trim()"
              @click="applySuggestion(activeReferenceSuggestion)"
            >
              应用到草稿
            </button>
          </div>
          <section v-if="previewText" class="consistency-preview" aria-label="应用预览">
            <p class="eyebrow">草稿预览</p>
            <pre>{{ previewText }}</pre>
          </section>
        </section>
        <section>
          <p class="eyebrow">依据说明</p>
          <p class="proposal-rationale">{{ activeReferenceSuggestion.rationale }}</p>
        </section>
        <section v-if="referenceWarnings(activeReferenceSuggestion).length">
          <p class="eyebrow">提醒与备注</p>
          <ul>
            <li v-for="item in referenceWarnings(activeReferenceSuggestion)" :key="item">
              {{ item }}
            </li>
          </ul>
        </section>
        <details>
          <summary>使用的上下文 · 展开查看</summary>
          <pre>{{ activeReferenceSuggestion.used_context }}</pre>
        </details>
      </section>
    </div>
  </section>
</template>
