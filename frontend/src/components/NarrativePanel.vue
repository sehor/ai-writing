<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { statusText } from '../utils/format'
import { useNarrativeStore } from '../stores/narrative'
import { useWorkspaceStore } from '../stores/workspace'
import { useManuscriptStore } from '../stores/manuscript'

withDefaults(defineProps<{ mode?: 'full' | 'maintenance' }>(), { mode: 'full' })

const narrative = useNarrativeStore()
const workspace = useWorkspaceStore()
const manuscript = useManuscriptStore()
const {
  threads, relations, director, error, isLoading,
  facts, activeFactId, activeFact, factDraft, factError, factStatus,
  isSavingFact, isRetractingFact, isLoadingFactDetails,
  knowledgeStates, history, activeKnowledgeId, activeKnowledge, knowledgeDraft,
  knowledgeError, knowledgeStatus, isSavingKnowledge, isRetractingKnowledge, knowledgeReadOnly,
  storyState, previewError, previewStatus, isLoadingPreview,
} = storeToRefs(narrative)

const scenes = computed(() => [...manuscript.sceneContracts].sort((a, b) => a.sequence - b.sequence))
const activeScene = computed(() => manuscript.activeSceneContract)
const previewScene = ref(activeScene.value?.sequence ?? scenes.value[0]?.sequence ?? 0)
const previewCharacter = ref(activeScene.value?.pov ?? '')
const retractFactReason = ref('')
const retractKnowledgeReason = ref('')

watch(
  () => [workspace.activeProjectId, activeScene.value?.id, activeScene.value?.sequence, activeScene.value?.pov] as const,
  ([, , sequence, pov]) => {
    if (typeof sequence === 'number') previewScene.value = sequence
    previewCharacter.value = pov ?? ''
  },
  { immediate: true },
)

function refreshAll() {
  if (!workspace.activeProjectId) return
  void narrative.load(workspace.activeProjectId, manuscript.activeSceneId)
  if (activeFactId.value) void narrative.loadFactDetails(workspace.activeProjectId, activeFactId.value)
}

function chooseFact(id: string) {
  void narrative.selectFact(id)
}

function chooseKnowledge(id: string) {
  narrative.selectKnowledge(id)
}

function preview() {
  void narrative.loadStoryState(Number(previewScene.value), previewCharacter.value)
}

function factTitle(item: typeof facts.value[number]) {
  return `${item.subject} · ${item.predicate}`
}

function knowledgeTitle(item: typeof knowledgeStates.value[number]) {
  if (item.scope === 'world_truth') return '世界真相'
  if (item.scope === 'reader_knowledge') return `读者 · 场景 ${item.known_from_scene}`
  return `${item.character} · 场景 ${item.known_from_scene}`
}
</script>

<template>
  <section class="narrative-panel">
    <section class="temporal-facts" aria-label="时态事实与知识">
      <div class="panel-header">
        <div>
          <p class="eyebrow">作者管理视图</p>
          <h3>时态事实与知识</h3>
          <p class="save-state">管理列表可查看未来与隐藏信息；正文安全上下文只使用下方场景预览对应的 story-state。</p>
        </div>
        <div class="button-row">
          <button type="button" class="secondary" :disabled="isLoading || !workspace.activeProjectId" @click="refreshAll">
            {{ isLoading ? '刷新中…' : '刷新事实' }}
          </button>
          <button type="button" class="primary" :disabled="!workspace.activeProjectId" @click="narrative.startNewFact">
            新建事实
          </button>
        </div>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="temporal-grid">
        <aside class="fact-list" data-testid="fact-list" aria-label="时态事实列表">
          <p v-if="!facts.length" class="empty-state">还没有时态事实。可创建第一条，并设置它在哪些场景有效、何时对读者可见。</p>
          <button
            v-for="item in facts"
            :key="item.id"
            type="button"
            :class="{ active: item.id === activeFactId }"
            @click="chooseFact(item.id)"
          >
            <span>{{ factTitle(item) }}</span>
            <small>{{ item.value }}</small>
            <small>场景 {{ item.valid_from_scene }}–{{ item.valid_to_scene ?? '持续' }} · {{ statusText(item.status) }} · v{{ item.version }}</small>
          </button>
        </aside>

        <section class="fact-editor" aria-label="事实编辑器">
          <div class="panel-header compact">
            <div>
              <p class="eyebrow">{{ activeFact ? `事实 v${activeFact.version}` : '新建事实' }}</p>
              <h4>{{ activeFact ? factTitle(activeFact) : '记录时态事实' }}</h4>
            </div>
            <span v-if="activeFact" class="step-chip">{{ statusText(activeFact.status) }}</span>
          </div>
          <div class="fact-fields two-column">
            <label><span>主体</span><input v-model="factDraft.subject" maxlength="160" placeholder="信件" /></label>
            <label><span>关系 / 属性</span><input v-model="factDraft.predicate" maxlength="160" placeholder="作者" /></label>
          </div>
          <label><span>事实内容</span><textarea v-model="factDraft.value" rows="3" maxlength="4000" placeholder="已经确认或计划中的事实" /></label>
          <div class="fact-fields three-column">
            <label><span>有效起始场景</span><input v-model.number="factDraft.valid_from_scene" type="number" min="0" max="999" /></label>
            <label><span>有效结束场景</span><input v-model.number="factDraft.valid_to_scene" type="number" min="0" max="999" placeholder="持续" /></label>
            <label><span>读者可见场景</span><input v-model.number="factDraft.reader_visible_from" type="number" min="0" max="999" placeholder="隐藏" /></label>
          </div>
          <div class="fact-fields two-column">
            <label><span>来源</span><input v-model="factDraft.source_ref" maxlength="240" placeholder="scene:S004 / author:note" /></label>
            <label><span>状态</span><select v-model="factDraft.status"><option value="confirmed">已确认</option><option value="planned">计划中</option><option v-if="activeFact?.status === 'retracted'" value="retracted">已撤回</option></select></label>
          </div>
          <label v-if="activeFact"><span>更正原因</span><textarea v-model="factDraft.reason" rows="2" maxlength="1000" placeholder="说明为什么更正，历史会保留旧版本" /></label>
          <p v-if="factError" class="error" role="alert">{{ factError }}</p>
          <p v-else-if="factStatus" class="save-state">{{ factStatus }}</p>
          <p v-else class="save-state">保存只维护事实记录；planned / 未来 / 隐藏信息不会自动成为当前场景的安全写作上下文。</p>
          <div class="button-row fact-actions">
            <button v-if="activeFact && activeFact.status !== 'retracted'" type="button" class="secondary danger" :disabled="isRetractingFact || !retractFactReason.trim()" @click="narrative.retractFact(retractFactReason)">撤回事实</button>
            <button type="button" class="primary" :disabled="isSavingFact" @click="narrative.saveFact">{{ isSavingFact ? '保存中…' : activeFact ? '保存更正' : '保存事实' }}</button>
          </div>
          <label v-if="activeFact && activeFact.status !== 'retracted'" class="retract-reason"><span>撤回原因</span><input v-model="retractFactReason" maxlength="1000" placeholder="仅撤回时使用" /></label>
        </section>
      </div>

      <section v-if="activeFact" class="knowledge-maintenance">
        <div class="panel-header compact">
          <div>
            <p class="eyebrow">知情范围</p>
            <h4>读者与角色知识</h4>
          </div>
          <div class="button-row">
            <button type="button" class="secondary" :disabled="activeFact.status !== 'confirmed'" @click="narrative.startNewKnowledge('reader_knowledge')">新建读者知识</button>
            <button type="button" class="secondary" :disabled="activeFact.status !== 'confirmed'" @click="narrative.startNewKnowledge('character_knowledge')">新建角色知识</button>
          </div>
        </div>
        <p v-if="isLoadingFactDetails" class="save-state">正在读取知识状态与历史…</p>
        <div class="knowledge-grid">
          <aside class="knowledge-list" aria-label="知识状态列表">
            <button v-for="item in knowledgeStates" :key="item.id" type="button" :class="{ active: item.id === activeKnowledgeId }" @click="chooseKnowledge(item.id)">
              <span>{{ knowledgeTitle(item) }}</span>
              <small>{{ statusText(item.status) }} · v{{ item.version }}</small>
            </button>
            <p v-if="!knowledgeStates.length" class="empty-state">除世界真相外，还没有读者或角色知情记录。</p>
          </aside>
          <section class="knowledge-editor" aria-label="知识状态编辑器">
            <p v-if="knowledgeReadOnly" class="save-state">世界真相由事实派生，不能单独编辑；请在上方更正事实本身。</p>
            <template v-else>
              <div class="fact-fields two-column">
                <label><span>知识类型</span><select v-model="knowledgeDraft.scope" :disabled="!!activeKnowledge"><option value="reader_knowledge">读者已知</option><option value="character_knowledge">角色已知</option></select></label>
                <label v-if="knowledgeDraft.scope === 'character_knowledge'"><span>角色</span><input v-model="knowledgeDraft.character" :disabled="!!activeKnowledge" maxlength="160" placeholder="林舟" /></label>
              </div>
              <div class="fact-fields two-column">
                <label><span>知情起始场景</span><input v-model.number="knowledgeDraft.known_from_scene" type="number" min="0" max="999" /></label>
                <label><span>来源</span><input v-model="knowledgeDraft.source_ref" maxlength="240" placeholder="scene:S004" /></label>
              </div>
              <label><span>状态</span><select v-model="knowledgeDraft.status"><option value="confirmed">已确认</option><option value="planned">待确认</option><option v-if="activeKnowledge?.status === 'retracted'" value="retracted">已撤回</option></select></label>
              <label><span>维护原因</span><textarea v-model="knowledgeDraft.reason" rows="2" maxlength="1000" placeholder="角色何时、为何得知；或说明更正原因" /></label>
              <p v-if="knowledgeError" class="error" role="alert">{{ knowledgeError }}</p>
              <p v-else-if="knowledgeStatus" class="save-state">{{ knowledgeStatus }}</p>
              <div class="button-row">
                <button v-if="activeKnowledge && activeKnowledge.status !== 'retracted'" type="button" class="secondary danger" :disabled="isRetractingKnowledge || !retractKnowledgeReason.trim()" @click="narrative.retractKnowledge(retractKnowledgeReason)">撤回知情记录</button>
                <button type="button" class="primary" :disabled="isSavingKnowledge" @click="narrative.saveKnowledge">{{ isSavingKnowledge ? '保存中…' : activeKnowledge ? '保存知识更正' : '保存知识状态' }}</button>
              </div>
              <label v-if="activeKnowledge && activeKnowledge.status !== 'retracted'" class="retract-reason"><span>撤回原因</span><input v-model="retractKnowledgeReason" maxlength="1000" placeholder="仅撤回时使用" /></label>
            </template>
          </section>
        </div>
        <details v-if="history.length" class="history-disclosure"><summary>更正历史 · {{ history.length }}</summary><ol><li v-for="revision in history" :key="revision.id"><strong>v{{ revision.version }}</strong> · {{ revision.reason }}<small>{{ revision.created_at }} · {{ revision.record.source_ref || '未标注来源' }}</small></li></ol></details>
      </section>

      <section class="story-state-preview" aria-label="场景知识预览">
        <div class="panel-header compact">
          <div>
            <p class="eyebrow">Scene-safe snapshot</p>
            <h4>同场景知识对照</h4>
          </div>
          <button type="button" class="primary" :disabled="isLoadingPreview || !workspace.activeProjectId" @click="preview">{{ isLoadingPreview ? '预览中…' : '预览场景知识' }}</button>
        </div>
        <div class="fact-fields two-column preview-controls">
          <label><span>预览场景</span><select v-if="scenes.length" v-model.number="previewScene" aria-label="预览场景"><option v-for="scene in scenes" :key="scene.id" :value="scene.sequence">{{ scene.sequence }} · {{ scene.title }}</option></select><input v-else v-model.number="previewScene" aria-label="预览场景" type="number" min="0" max="999" /></label>
          <label><span>预览角色</span><input v-model="previewCharacter" aria-label="预览角色" maxlength="160" placeholder="留空只比较世界与读者" /></label>
        </div>
        <p class="save-state">此区域只读取后端 `/story-state` 的安全结果。管理列表中的未来/隐藏事实不会因在这里可见而进入正文生成上下文。</p>
        <p v-if="previewError" class="error" role="alert">{{ previewError }}</p>
        <p v-else-if="previewStatus" class="save-state">{{ previewStatus }}</p>
        <div v-if="storyState" class="story-state-columns">
          <section><h5>世界真相</h5><article v-for="item in storyState.world_truth" :key="item.id"><strong>{{ item.subject }} · {{ item.predicate }}</strong><p>{{ item.value }}</p><small>来源 {{ item.source_ref || '未标注' }} · v{{ item.version }}</small></article><p v-if="!storyState.world_truth.length" class="empty-state">此场景没有有效的已确认世界事实。</p></section>
          <section><h5>读者已知</h5><article v-for="item in storyState.reader_knowledge" :key="item.id"><strong>{{ item.subject }} · {{ item.predicate }}</strong><p>{{ item.value }}</p><small>来源 {{ item.source_ref || '未标注' }} · v{{ item.version }}</small></article><p v-if="!storyState.reader_knowledge.length" class="empty-state">截至此场景，读者还不知道这些事实。</p></section>
          <section><h5>{{ storyState.character || previewCharacter || '角色' }}已知</h5><article v-for="item in storyState.character_knowledge" :key="item.id"><strong>{{ item.subject }} · {{ item.predicate }}</strong><p>{{ item.value }}</p><small>来源 {{ item.source_ref || '未标注' }} · v{{ item.version }}</small></article><p v-if="!storyState.character_knowledge.length" class="empty-state">截至此场景，该角色没有额外的已确认知情事实。</p></section>
        </div>
        <p v-else class="empty-state">选择场景与角色后预览，即可对照世界真相、读者已知和角色已知。</p>
      </section>
    </section>

    <template v-if="mode === 'full'">
      <div class="panel-header structural-heading">
        <div><h3>故事线与已确认关系</h3></div>
        <button type="button" class="secondary" :disabled="isLoading || !workspace.activeProjectId" @click="refreshAll">刷新叙事状态</button>
      </div>
      <p v-if="!threads.length && !relations.length" class="empty-state">尚无故事线或已确认关系。CLP 提案经人工接受后会出现在这里。</p>
      <div v-if="threads.length" class="narrative-threads">
        <article v-for="thread in threads" :key="thread.id" :data-thread-id="thread.id">
          <strong>{{ thread.title }}</strong> <span class="step-chip">{{ thread.status }}</span>
          <p>{{ thread.thread_type }} · 重要度 {{ thread.importance }} · 预计回收 {{ thread.target_payoff_from ?? '未设定' }}–{{ thread.target_payoff_to ?? '未设定' }}</p>
        </article>
      </div>
      <table v-if="relations.length" class="writeback-changes">
        <thead><tr><th>来源</th><th>关系</th><th>目标</th><th>有效场景</th><th>置信度</th></tr></thead>
        <tbody><tr v-for="relation in relations" :key="relation.id"><td>{{ relation.source }}</td><td>{{ relation.relation }}</td><td>{{ relation.target }}</td><td>{{ relation.valid_from }}–{{ relation.valid_to ?? '持续' }}</td><td>{{ relation.confidence }}</td></tr></tbody>
      </table>
      <section v-if="director" class="director-report">
        <h4>Director · 场景 {{ director.scene_sequence }}</h4>
        <p class="empty-state">以下仅为结构建议，不会自动修改故事状态。</p>
        <p v-if="!director.findings.length">当前场景没有结构提示。</p>
        <article v-for="(finding, index) in director.findings" :key="`${finding.code}-${index}`"><strong>{{ finding.title }}</strong> <span class="severity-chip">{{ finding.severity }}</span><p>{{ finding.detail }}</p></article>
      </section>
    </template>
  </section>
</template>

<style scoped>
.temporal-facts,
.knowledge-maintenance,
.story-state-preview {
  display: grid;
  gap: 16px;
}

.temporal-facts {
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}

.temporal-grid,
.knowledge-grid,
.story-state-columns {
  display: grid;
  grid-template-columns: minmax(180px, 0.8fr) minmax(0, 2fr);
  gap: 16px;
}

.fact-list,
.knowledge-list {
  display: grid;
  align-content: start;
  gap: 8px;
}

.fact-list button,
.knowledge-list button {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
}

.fact-list button.active,
.knowledge-list button.active {
  border-color: var(--accent);
}

.fact-editor,
.knowledge-editor,
.story-state-columns > section {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
}

.fact-fields {
  display: grid;
  gap: 10px;
}

.fact-fields.two-column {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.fact-fields.three-column,
.story-state-columns {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.fact-actions {
  justify-content: flex-end;
}

.retract-reason {
  max-width: 520px;
}

.story-state-columns article {
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}

.story-state-columns article:last-of-type {
  border-bottom: 0;
}

.story-state-columns p,
.story-state-columns small,
.history-disclosure small {
  display: block;
  margin: 4px 0 0;
}

.history-disclosure ol {
  display: grid;
  gap: 8px;
}

.structural-heading {
  margin-top: 20px;
}

@media (max-width: 900px) {
  .temporal-grid,
  .knowledge-grid,
  .story-state-columns,
  .fact-fields.two-column,
  .fact-fields.three-column {
    grid-template-columns: 1fr;
  }
}
</style>
