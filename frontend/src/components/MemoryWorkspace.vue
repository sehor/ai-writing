<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { statusText } from '../utils/format'
import { useMemoryStore } from '../stores/memory'

const store = useMemoryStore()
const {
  memoryRecords,
  activeMemoryId,
  isSavingMemory,
  isDeletingMemory,
  memoryError,
  memoryDraft,
  memoryStateLabel,
} = storeToRefs(store)
const { startNewMemoryRecord, saveMemoryRecord, deleteMemoryRecord } = store
const query = ref('')
const typeFilter = ref('')
const recordTypes = computed(() => [
  ...new Set(memoryRecords.value.map((item) => item.record_type)),
])
const filteredRecords = computed(() =>
  memoryRecords.value.filter(
    (item) =>
      (!typeFilter.value || item.record_type === typeFilter.value) &&
      JSON.stringify(item).toLowerCase().includes(query.value.toLowerCase()),
  ),
)
</script>

<template>
  <section class="memory-workspace">
    <div class="panel-header">
      <div>
        <h3>记忆与文风记录</h3>
      </div>
      <button class="primary" type="button" @click="startNewMemoryRecord">
        新建记忆
      </button>
    </div>

    <div class="memory-grid">
      <aside class="memory-list" aria-label="Memory and style records">
        <label class="list-search"
          ><span class="sr-only">搜索记忆</span
          ><input v-model="query" placeholder="搜索记忆" /></label
        ><select v-model="typeFilter" aria-label="筛选记忆类型">
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
          v-for="record in filteredRecords"
          :key="record.id"
          :class="{ active: record.id === activeMemoryId }"
          type="button"
          @click="activeMemoryId = record.id"
        >
          <span>{{ record.title }}</span>
          <small>{{ statusText(record.record_type) }}</small>
        </button>
        <p v-if="memoryRecords.length === 0" class="empty-state">
          还没有记忆与文风记录。
        </p>
      </aside>

      <form class="memory-editor" @submit.prevent="saveMemoryRecord">
        <div class="memory-fields">
          <label>
            <span>类型</span>
            <select v-model="memoryDraft.record_type">
              <option value="chapter_summary">章节摘要</option>
              <option value="prose_sample">正文样本</option>
              <option value="voice_sample">人物声音样本</option>
              <option value="style_rule">文风规则</option>
            </select>
          </label>
          <label>
            <span>标题</span>
            <input
              v-model="memoryDraft.title"
              autocomplete="off"
              placeholder="第三章回顾"
            />
          </label>
        </div>

        <div class="memory-fields">
          <label>
            <span>范围</span>
            <input
              v-model="memoryDraft.scope"
              placeholder="如：第三章、人物声音、城市描写"
            />
          </label>
          <label>
            <span>来源</span>
            <input
              v-model="memoryDraft.source_ref"
              placeholder="如：正文第三章"
            />
          </label>
        </div>

        <label>
          <span>内容</span>
          <textarea
            v-model="memoryDraft.content"
            rows="10"
            placeholder="填写摘要、正文样本、人物声音或文风规则。"
          />
        </label>
        <label>
          <span>标签</span>
          <input
            v-model="memoryDraft.tags"
            placeholder="如：悬念、林野、档案馆"
          />
        </label>

        <div class="form-actions artifact-actions">
          <p v-if="memoryError" class="error">{{ memoryError }}</p>
          <p v-else class="save-state">{{ memoryStateLabel }}</p>
          <div class="button-row">
            <button
              v-if="activeMemoryId"
              class="secondary danger"
              type="button"
              :disabled="isDeletingMemory"
              @click="deleteMemoryRecord"
            >
              {{ isDeletingMemory ? '删除中…' : '删除' }}
            </button>
            <button class="primary" type="submit" :disabled="isSavingMemory">
              {{
                isSavingMemory
                  ? '保存中…'
                  : activeMemoryId
                    ? '保存记录'
                    : '创建记录'
              }}
            </button>
          </div>
        </div>
      </form>
    </div>
  </section>
</template>
