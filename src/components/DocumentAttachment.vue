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
    
    <div class="doc-expand-icon">
      {{ expanded ? '▼' : '▶' }}
    </div>
  </div>
  
  <!-- 展开的 markdown 内容 -->
  <div v-if="expanded && attachment.markdownContent" class="doc-content">
    <MarkdownRenderer :content="attachment.markdownContent" :done="true" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  attachment: {
    type: Object,
    required: true
  }
})

const expanded = ref(false)

function toggleExpand() {
  if (props.attachment.markdownContent) {
    expanded.value = !expanded.value
  }
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
  padding: 10px 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  min-width: 200px;
  max-width: 300px;
}

.doc-attachment:hover {
  background: #1e293b;
  border-color: #6366f1;
}

.doc-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
}

.doc-icon svg {
  width: 100%;
  height: 100%;
}

.icon-pdf { color: #ef4444; }
.icon-word { color: #3b82f6; }
.icon-excel { color: #10b981; }
.icon-ppt { color: #f97316; }
.icon-text { color: #64748b; }
.icon-file { color: #94a3b8; }

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 13px;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-size {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.doc-expand-icon {
  flex-shrink: 0;
  color: #64748b;
  font-size: 12px;
}

.doc-content {
  margin-top: 8px;
  padding: 12px;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  max-height: 400px;
  overflow-y: auto;
}
</style>
