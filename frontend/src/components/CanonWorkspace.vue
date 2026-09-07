<script setup lang="ts">
import { computed, ref } from 'vue'
import { statusText } from '../utils/format'
import { storeToRefs } from 'pinia'
import { useCanonStore } from '../stores/canon'
import NarrativePanel from './NarrativePanel.vue'

const store = useCanonStore()
const {
  canonEntities,
  activeCanonId,
  isSavingCanon,
  isDeletingCanon,
  canonError,
  canonDraft,
  canonStateLabel,
} = storeToRefs(store)
const { startNewCanonEntity, saveCanonEntity, deleteCanonEntity } = store
const query = ref('')
const typeFilter = ref('')
const recordTypes = computed(() => [
  ...new Set(canonEntities.value.map((item) => item.entity_type)),
])
const filteredRecords = computed(() =>
  canonEntities.value.filter(
    (item) =>
      (!typeFilter.value || item.entity_type === typeFilter.value) &&
      JSON.stringify(item).toLowerCase().includes(query.value.toLowerCase()),
  ),
)
</script>

<template>
  <section class="canon-workspace">
    <div class="panel-header">
      <div>
        <h3>已确认的故事事实</h3>
      </div>
      <button class="primary" type="button" @click="startNewCanonEntity">
        新建设定
      </button>
    </div>

    <div class="canon-grid">
      <aside class="canon-list" aria-label="Canon entities">
        <label class="list-search"
          ><span class="sr-only">搜索设定</span
          ><input v-model="query" placeholder="搜索设定" /></label
        ><select v-model="typeFilter" aria-label="筛选设定类型">
          <option value="">全部类型</option>
          <option v-for="type in recordTypes" :key="type" :value="type">
            {{ statusText(type) }}
          </option>
        </select>
        <p v-if="!filteredRecords.length" class="empty-state">
          {{
            query || typeFilter
              ? '没有匹配的记录。'
              : '还没有记录，建立第一条吧。'
          }}
        </p>
        <button
          v-for="entity in filteredRecords"
          :key="entity.id"
          :class="{ active: entity.id === activeCanonId }"
          type="button"
          @click="activeCanonId = entity.id"
        >
          <span>{{ entity.name }}</span>
          <small>{{ statusText(entity.entity_type) }}</small>
        </button>
        <p v-if="canonEntities.length === 0" class="empty-state">
          还没有故事设定。
        </p>
      </aside>

      <form class="canon-editor" @submit.prevent="saveCanonEntity">
        <div class="canon-fields">
          <label>
            <span>类型</span>
            <select v-model="canonDraft.entity_type">
              <option value="character">人物</option>
              <option value="location">地点</option>
              <option value="item">物品</option>
              <option value="faction">组织</option>
              <option value="rule">规则</option>
            </select>
          </label>
          <label>
            <span>名称</span>
            <input
              v-model="canonDraft.name"
              autocomplete="off"
              placeholder="林野"
            />
          </label>
        </div>

        <label>
          <span>摘要</span>
          <textarea
            v-model="canonDraft.summary"
            rows="3"
            placeholder="这个人物、地点或规则是什么，为何重要？"
          />
        </label>
        <label>
          <span>当前状态</span>
          <textarea
            v-model="canonDraft.current_state"
            rows="4"
            placeholder="记录当前故事中已经确认的事实。"
          />
        </label>
        <label>
          <span>约束条件</span>
          <textarea
            v-model="canonDraft.constraints"
            rows="4"
            placeholder="后续写作必须遵守的事实与边界。"
          />
        </label>
        <div class="canon-fields">
          <label>
            <span>最后出现位置</span>
            <input
              v-model="canonDraft.last_seen"
              placeholder="如：第十二章或场景 S032"
            />
          </label>
        </div>
        <label>
          <span>时间线备注</span>
          <textarea
            v-model="canonDraft.timeline_notes"
            rows="5"
            placeholder="按章节或场景记录重要变化。"
          />
        </label>

        <div class="form-actions artifact-actions">
          <p v-if="canonError" class="error">{{ canonError }}</p>
          <p v-else class="save-state">{{ canonStateLabel }}</p>
          <div class="button-row">
            <button
              v-if="activeCanonId"
              class="secondary danger"
              type="button"
              :disabled="isDeletingCanon"
              @click="deleteCanonEntity"
            >
              {{ isDeletingCanon ? '删除中…' : '删除' }}
            </button>
            <button class="primary" type="submit" :disabled="isSavingCanon">
              {{
                isSavingCanon
                  ? '保存中…'
                  : activeCanonId
                    ? '保存设定'
                    : '创建设定'
              }}
            </button>
          </div>
        </div>
      </form>
    </div>

    <details class="graph-detail-disclosure" open>
      <summary>时态事实与知识</summary>
      <NarrativePanel mode="maintenance" />
    </details>
  </section>
</template>
