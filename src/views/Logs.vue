<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">日志</h1>
      <p class="page-subtitle">服务运行日志与事件记录</p>
    </header>

    <section class="card">
      <div class="card-header">
        <span>运行日志</span>
        <div class="header-actions">
          <span class="log-count">共 {{ logs.length }} 条</span>
          <label class="auto-scroll">
            <input type="checkbox" v-model="autoScroll" />
            <span>自动滚动到底部</span>
          </label>
          <button class="btn-export" :disabled="logs.length === 0" @click="exportLogs">
            导出日志
          </button>
        </div>
      </div>
      <div class="card-body log-container" ref="containerRef">
        <div v-for="(log, index) in logs" :key="index" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-level" :class="log.level">{{ levelLabel(log.level) }}</span>
          <span class="log-text">{{ log.text }}</span>
        </div>
        <div v-if="logs.length === 0" class="log-empty">暂无日志...</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'

// 最大显示行数，超出后丢弃最旧日志
const MAX_LINES = 500

// logs: [{ time: 'HH:MM:SS', level: 'info|warn|error|debug', text, ts }]
const logs = ref([])
const autoScroll = ref(true)
const containerRef = ref(null)

function levelLabel(level) {
  return (level || 'info').toUpperCase()
}

function formatTime(ts) {
  const t = new Date(ts || Date.now())
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`
}

function appendLog(entry) {
  logs.value.push({
    time: formatTime(entry.ts),
    level: (entry.level || 'info').toLowerCase(),
    text: entry.text ?? '',
    ts: entry.ts || Date.now()
  })
  if (logs.value.length > MAX_LINES) {
    logs.value.splice(0, logs.value.length - MAX_LINES)
  }
  if (autoScroll.value) {
    scrollToBottom()
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = containerRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 勾选自动滚动时立即滚到底部
watch(autoScroll, (v) => {
  if (v) scrollToBottom()
})

async function exportLogs() {
  if (!window.electronAPI || logs.value.length === 0) return
  const payload = logs.value.map((l) => ({ ts: l.ts, level: l.level, text: l.text }))
  const result = await window.electronAPI.exportLogs(payload)
  if (result && !result.success && !result.canceled) {
    console.error('导出日志失败:', result.message)
  }
}

onMounted(() => {
  if (!window.electronAPI) return
  // 订阅 type=log 消息推送
  window.electronAPI.onLogUpdate(appendLog)
  // 拉取历史缓冲（页面挂载可能晚于日志产生）
  window.electronAPI.getLogs().then((history) => {
    if (Array.isArray(history)) {
      history.slice(-MAX_LINES).forEach(appendLog)
    }
  })
})

onUnmounted(() => {
  if (window.electronAPI) {
    window.electronAPI.removeAllListeners('log-update')
  }
})
</script>

<style scoped>
.page {
  max-width: 1200px;
}

.page-header {
  margin-bottom: 28px;
}

.page-title {
  font-size: 30px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 8px;
}

.page-subtitle {
  font-size: 15px;
  color: #64748b;
}

.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 14px;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  font-size: 17px;
  font-weight: 600;
  color: #e2e8f0;
  border-bottom: 1px solid #334155;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 18px;
}

.log-count {
  font-size: 13px;
  font-weight: 400;
  color: #64748b;
}

.auto-scroll {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 400;
  color: #94a3b8;
  cursor: pointer;
  user-select: none;
}

.auto-scroll input {
  accent-color: #4f46e5;
  cursor: pointer;
}

.btn-export {
  background: #273449;
  border: 1px solid #334155;
  color: #cbd5e1;
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-export:hover:not(:disabled) {
  background: #4f46e5;
  border-color: #4f46e5;
  color: #ffffff;
}

.btn-export:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.card-body {
  padding: 16px 24px;
}

/* ===== 日志列表 ===== */
.log-container {
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.log-container::-webkit-scrollbar {
  width: 6px;
}

.log-container::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 3px;
}

.log-line {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #273449;
}

.log-line:last-child {
  border-bottom: none;
}

.log-time {
  color: #64748b;
  flex-shrink: 0;
}

.log-level {
  flex-shrink: 0;
  width: 52px;
  font-weight: 700;
  font-size: 11px;
}

.log-level.debug { color: #64748b; }
.log-level.info { color: #38bdf8; }
.log-level.warn { color: #fbbf24; }
.log-level.error { color: #ef4444; }

.log-text {
  color: #cbd5e1;
  word-break: break-all;
  white-space: pre-wrap;
}

.log-empty {
  color: #64748b;
  text-align: center;
  padding: 40px 0;
}
</style>
