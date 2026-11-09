<template>
  <div class="page">
    <header class="page-header">
      <div class="header-main">
        <div class="eyebrow">
          <AppIcon name="terminal" :size="12" />
          运行记录
        </div>
        <h1 class="page-title">日志</h1>
        <p class="page-subtitle">服务运行日志与事件记录</p>
      </div>
      <div class="header-actions">
        <button class="btn-export" :disabled="logs.length === 0" @click="exportLogs">
          <AppIcon name="download" :size="14" />
          导出日志
        </button>
      </div>
    </header>

    <section class="card log-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="toolbar-icon"><AppIcon name="terminal" :size="14" /></span>
          <span class="toolbar-title">运行日志</span>
          <span class="log-count">共 {{ logs.length }} 条</span>
        </div>
        <label class="auto-scroll">
          <input type="checkbox" v-model="autoScroll" />
          <span class="switch" aria-hidden="true"></span>
          <span class="auto-scroll-label">自动滚动到底部</span>
        </label>
      </div>

      <div class="card-body log-container" ref="containerRef">
        <div v-for="(log, index) in logs" :key="index" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-level" :class="log.level">{{ levelLabel(log.level) }}</span>
          <span class="log-text">{{ log.text }}</span>
        </div>
        <div v-if="logs.length === 0" class="ui-empty log-empty">
          <div class="ui-empty-icon"><AppIcon name="terminal" :size="22" /></div>
          <div class="ui-empty-title">暂无日志...</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'

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
  max-width: 1180px;
  margin: 0 auto;
  animation: fadeUp var(--dur-slow) var(--ease-out) backwards;
}

/* ===== 页头 ===== */
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.header-main {
  min-width: 0;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--amber-500);
  margin-bottom: 8px;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
  color: var(--text-1);
}

.page-subtitle {
  margin-top: 7px;
  font-size: 13px;
  color: var(--text-3);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn-export {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 13px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}

.btn-export:hover:not(:disabled) {
  color: var(--text-1);
  background: var(--ink-700);
  border-color: var(--line-3);
}

.btn-export:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ===== 日志卡 ===== */
.card {
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, var(--ink-850), var(--ink-800));
  border: 1px solid var(--line-1);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1), var(--hairline);
  overflow: hidden;
}

/* 工具条：一块内凹的深色控制面板，像终端窗口的标题栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 12px 14px 0;
  padding: 7px 10px 7px 11px;
  background: var(--ink-1000);
  border: 1px solid var(--line-1);
  border-radius: var(--r-md);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.035),
    inset 0 10px 22px -18px rgba(0, 0, 0, 0.9);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.toolbar-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--amber-400);
}

.toolbar-title {
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-2);
  white-space: nowrap;
}

.log-count {
  display: inline-flex;
  align-items: center;
  height: 19px;
  padding: 0 8px;
  border-radius: var(--r-full);
  font-size: 10.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-4);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--line-1);
  white-space: nowrap;
}

/* 自动滚动：自绘开关，去掉原生复选框 */
.auto-scroll {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}

.auto-scroll input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.switch {
  position: relative;
  width: 30px;
  height: 17px;
  flex-shrink: 0;
  border-radius: var(--r-full);
  background: var(--ink-700);
  border: 1px solid var(--line-2);
  transition: background var(--dur) var(--ease-out), border-color var(--dur) var(--ease-out);
}

.switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--text-4);
  transition: transform var(--dur) var(--ease-out), background var(--dur) var(--ease-out);
}

.auto-scroll:hover .switch {
  border-color: var(--line-3);
}

.auto-scroll input:checked + .switch {
  background: var(--amber-a20);
  border-color: var(--amber-a55);
}

.auto-scroll input:checked + .switch::after {
  transform: translateX(13px);
  background: var(--amber-300);
}

.auto-scroll input:focus-visible + .switch {
  outline: 2px solid var(--amber-a55);
  outline-offset: 2px;
}

.auto-scroll-label {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
  transition: color var(--dur-fast) var(--ease-out);
}

.auto-scroll:hover .auto-scroll-label {
  color: var(--text-2);
}

/* ===== 日志列表 ===== */
.card-body {
  padding: 0;
}

.log-container {
  max-height: calc(100vh - 316px);
  overflow-y: auto;
  overflow-x: hidden;
  padding: 6px 16px 14px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.65;
}

.log-container::-webkit-scrollbar {
  width: 8px;
}

.log-container::-webkit-scrollbar-thumb {
  background: var(--ink-600);
  border-radius: var(--r-full);
  border: 2px solid transparent;
  background-clip: padding-box;
}

.log-container::-webkit-scrollbar-thumb:hover {
  background: var(--line-3);
  background-clip: padding-box;
}

.log-line {
  display: grid;
  grid-template-columns: 62px 54px minmax(0, 1fr);
  align-items: start;
  gap: 10px;
  margin: 0 -8px;
  padding: 7px 8px;
  border-bottom: 1px solid var(--line-1);
  border-radius: var(--r-xs);
  transition: background var(--dur-fast) var(--ease-out);
}

.log-line:hover {
  background: rgba(255, 255, 255, 0.025);
}

.log-line:last-of-type {
  border-bottom: none;
}

.log-time {
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  white-space: nowrap;
  padding-top: 1px;
}

.log-level {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 46px;
  height: 18px;
  margin-top: 1px;
  padding: 0 7px;
  border-radius: var(--r-full);
  border: 1px solid transparent;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 0.06em;
}

.log-level.info {
  color: var(--jade-400);
  background: var(--jade-a12);
  border-color: rgba(126, 203, 161, 0.22);
}

.log-level.warn {
  color: var(--amber-300);
  background: var(--amber-a12);
  border-color: var(--amber-a20);
}

.log-level.error {
  color: var(--coral-400);
  background: var(--coral-a12);
  border-color: rgba(233, 119, 110, 0.22);
}

.log-level.debug {
  color: var(--text-4);
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--line-1);
}

.log-text {
  min-width: 0;
  color: var(--text-2);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
}

/* 空态：沿用原插槽文案，只换视觉 */
.log-empty {
  padding: 52px 16px 56px;
}

/* ===== 响应式 ===== */
@media (max-width: 980px) {
  .page-title {
    font-size: 23px;
  }

  .log-container {
    max-height: calc(100vh - 288px);
    padding: 6px 12px 12px;
  }

  .log-line {
    grid-template-columns: 62px 50px minmax(0, 1fr);
    gap: 8px;
  }

  .log-level {
    min-width: 42px;
    padding: 0 6px;
  }
}

@media (max-width: 620px) {
  .toolbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .log-container {
    padding: 4px 8px 10px;
  }

  .log-line {
    grid-template-columns: 60px 44px minmax(0, 1fr);
    gap: 6px;
    margin: 0 -4px;
    padding: 6px 4px;
  }

  .log-level {
    min-width: 38px;
    padding: 0 4px;
    font-size: 9px;
  }
}
</style>
