<template>
  <div class="present-card">
    <div class="present-head">
      <span class="present-icon"><AppIcon name="package" :size="16" /></span>
      <div class="present-head-main">
        <div class="present-title">{{ data.title }}</div>
        <div class="present-sub">
          <span v-if="data.summary">{{ data.summary }}</span>
          <span v-else>共 {{ data.files.length }} 个文件</span>
        </div>
      </div>
      <div v-if="data.hasDiff" class="present-diff">
        <span class="add">+{{ formatNum(data.totalAdded) }}</span>
        <span class="del">-{{ formatNum(data.totalRemoved) }}</span>
      </div>
    </div>

    <div class="present-files">
      <button
        v-for="f in visibleFiles"
        :key="f.absolute || f.path"
        type="button"
        class="present-file"
        :title="`打开 ${f.path}`"
        @click="openFile(f)"
      >
        <span class="pf-icon"><AppIcon name="file" :size="13" /></span>
        <span class="pf-main">
          <span class="pf-name">{{ f.name }}</span>
          <span class="pf-path">{{ f.path }}</span>
        </span>
        <span class="pf-stats">
          <template v-if="f.added !== null || f.removed !== null">
            <span v-if="f.added" class="add">+{{ formatNum(f.added) }}</span>
            <span v-if="f.removed" class="del">-{{ formatNum(f.removed) }}</span>
          </template>
          <span v-else-if="f.lines" class="lines">{{ formatNum(f.lines) }} 行</span>
          <span v-else class="lines">{{ formatSize(f.size) }}</span>
        </span>
        <span class="pf-open">打开</span>
      </button>
    </div>

    <button
      v-if="data.files.length > PREVIEW_COUNT"
      type="button"
      class="present-more"
      @click="showAll = !showAll"
    >
      <AppIcon :name="showAll ? 'chevron-up' : 'chevron-down'" :size="12" />
      {{ showAll ? '收起' : `全部 ${data.files.length} 个文件` }}
    </button>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  data: { type: Object, required: true },
})

const PREVIEW_COUNT = 4
const showAll = ref(false)
const visibleFiles = computed(() =>
  showAll.value ? props.data.files : props.data.files.slice(0, PREVIEW_COUNT)
)

function formatNum(n) {
  return Number(n || 0).toLocaleString('en-US')
}

function formatSize(bytes) {
  const n = Number(bytes || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function openFile(file) {
  if (!file.absolute) return
  window.electronAPI?.openPath?.(file.absolute)
}
</script>

<style scoped>
.present-card {
  margin: 8px 0 10px;
  overflow: hidden;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.015));
  border: 1px solid var(--line-2);
  border-radius: 11px;
  max-width: 680px;
}

.present-head {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line-1);
}

.present-icon {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--amber-300);
  background: var(--amber-a12);
  border: 1px solid var(--amber-a20);
  border-radius: 8px;
}

.present-head-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.present-title {
  color: var(--text-1);
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.present-sub {
  color: var(--text-4);
  font-size: 10.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.present-diff {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.add { color: #6ECF9B; }
.del { color: #E9776E; }

.present-files {
  display: flex;
  flex-direction: column;
}

.present-file {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 12px;
  text-align: left;
  font-family: inherit;
  background: transparent;
  border: none;
  border-top: 1px solid rgba(255, 255, 255, 0.035);
  cursor: pointer;
}

.present-file:first-child { border-top: none; }

.present-file:hover { background: rgba(255, 255, 255, 0.035); }

.pf-icon {
  flex-shrink: 0;
  color: var(--text-4);
}

.pf-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.pf-name {
  flex-shrink: 0;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-2);
  font-size: 12px;
}

.pf-path {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-4);
  font-size: 10px;
}

.pf-stats {
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}

.lines { color: var(--text-4); }

.pf-open {
  flex-shrink: 0;
  width: 30px;
  color: var(--text-4);
  font-size: 10px;
  opacity: 0;
  transition: opacity var(--dur-fast), color var(--dur-fast);
}

.present-file:hover .pf-open {
  opacity: 1;
  color: var(--amber-300);
}

.present-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 100%;
  padding: 7px 12px;
  color: var(--text-3);
  font-family: inherit;
  font-size: 10.5px;
  background: rgba(0, 0, 0, 0.12);
  border: none;
  border-top: 1px solid var(--line-1);
  cursor: pointer;
}

.present-more:hover { color: var(--amber-300); }

@media (max-width: 720px) {
  .pf-path { display: none; }
  .pf-open { display: none; }
}
</style>
