<template>
  <div class="doc-attachment" @click="toggleExpand">
    <div class="doc-icon">
      <!-- PDF -->
      <svg v-if="isPdf" class="icon-pdf" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h5v7h7v9H6z"/>
        <text x="7" y="17" font-size="6" font-weight="bold" fill="currentColor">PDF</text>
      </svg>
      
      <!-- Word -->
      <svg v-else-if="isWord" class="icon-word" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h5v7h7v9H6z"/>
        <text x="7" y="17" font-size="5" font-weight="bold" fill="currentColor">DOC</text>
      </svg>
      
      <!-- Excel -->
      <svg v-else-if="isExcel" class="icon-excel" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h5v7h7v9H6z"/>
        <text x="7" y="17" font-size="5" font-weight="bold" fill="currentColor">XLS</text>
      </svg>
      
      <!-- PowerPoint -->
      <svg v-else-if="isPowerPoint" class="icon-ppt" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h5v7h7v9H6z"/>
        <text x="7" y="17" font-size="5" font-weight="bold" fill="currentColor">PPT</text>
      </svg>
      
      <!-- Text/Markdown -->
      <svg v-else-if="isText" class="icon-text" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h5v7h7v9H6z"/>
        <text x="7" y="17" font-size="5" font-weight="bold" fill="currentColor">TXT</text>
      </svg>
      
      <!-- Generic file -->
      <svg v-else class="icon-file" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 2l5 5h-5V4zM6 20V4h5v7h7v9H6z"/>
      </svg>
    </div>
    
    <div class="doc-info">
      <div class="doc-name">{{ attachment.fileName }}</div>
      <div class="doc-size">{{ formatSize(attachment.fileSize) }}</div>
    </div>
    
    <div class="doc-expand-icon" :class="{ expanded }">
      <AppIcon name="chevron-right" :size="12" />
    </div>
  </div>
  
  <!-- 展开内容：有 markdown 时渲染；无内容（如未开启 OCR 解析）时给出提示，
       保证文档图标始终可点击 -->
  <div v-if="expanded" class="doc-content">
    <MarkdownRenderer v-if="attachment.markdownContent" :content="attachment.markdownContent" :done="true" />
    <div v-else class="doc-empty">暂无内容（未开启 OCR 解析或解析结果为空）</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  attachment: {
    type: Object,
    required: true
  }
})

const expanded = ref(false)

function toggleExpand() {
  // 无内容也可展开（展示"暂无内容"提示），保证文档图标始终可点击
  expanded.value = !expanded.value
}

const isPdf = computed(() => props.attachment.fileExt?.toLowerCase() === '.pdf')
const isWord = computed(() => ['.doc', '.docx'].includes(props.attachment.fileExt?.toLowerCase()))
const isExcel = computed(() => ['.xls', '.xlsx'].includes(props.attachment.fileExt?.toLowerCase()))
const isPowerPoint = computed(() => ['.ppt', '.pptx'].includes(props.attachment.fileExt?.toLowerCase()))
const isText = computed(() => ['.txt', '.md'].includes(props.attachment.fileExt?.toLowerCase()))

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.doc-attachment {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 11px;
  min-width: 200px;
  max-width: 320px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast);
}

.doc-attachment:hover {
  background: rgba(255, 255, 255, 0.045);
  border-color: var(--amber-a35);
}

.doc-icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.doc-icon svg {
  width: 100%;
  height: 100%;
}

/* 文件类型色：压低饱和度，与整站的"低饱和 + 单一主色"保持一致 */
.icon-pdf { color: var(--coral-400); }
.icon-word { color: var(--azure-400); }
.icon-excel { color: var(--jade-400); }
.icon-ppt { color: var(--amber-400); }
.icon-text { color: var(--text-3); }
.icon-file { color: var(--text-3); }

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 12.5px;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-size {
  margin-top: 2px;
  font-size: 10.5px;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}

.doc-expand-icon {
  display: flex;
  flex-shrink: 0;
  color: var(--text-4);
  transition: transform var(--dur) var(--ease-out);
}

.doc-expand-icon.expanded {
  transform: rotate(90deg);
  color: var(--amber-400);
}

.doc-content {
  margin-top: 8px;
  padding: 12px 14px;
  max-height: 400px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.22);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
}

.doc-empty {
  font-size: 12px;
  color: var(--text-4);
}
</style>
