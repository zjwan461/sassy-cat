<template>
  <div class="page chat-page">
    <header class="page-header">
      <h1 class="page-title">AI 聊天</h1>
      <p class="page-subtitle">
        与臭屁猫对话
        <span class="conn" :class="connClass">{{ connText }}</span>
      </p>
    </header>

    <section class="card chat-card">
      <!-- 消息流 -->
      <div class="msg-list" ref="listRef">
        <div v-if="messages.length === 0" class="empty-hint">
          <div class="empty-emoji">🐱</div>
          <p>喵？有什么事就说吧，本喵听着呢。</p>
        </div>
        <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
          <div class="msg-avatar">{{ m.role === 'user' ? '🧑' : '🐱' }}</div>
          <div class="msg-body">
            <!-- 深度思考区域：可折叠，仅在有助手消息且存在 reasoning 内容时显示 -->
            <details v-if="m.reasoning" class="reasoning-block" :open="m.reasoningOpen">
              <summary class="reasoning-summary">💭 深度思考<span v-if="m.thinking" class="thinking-dot">…</span></summary>
              <div class="reasoning-content">{{ m.reasoning }}</div>
            </details>
            <div class="msg-content" :class="{ 'md-mode': isAssistant(m) }">
              <template v-if="isAssistant(m)">
                <MarkdownRenderer :content="m.content" :done="!m.streaming" />
                <span v-if="m.streaming" class="cursor">▌</span>
              </template>
              <template v-else>{{ m.content }}<span v-if="m.streaming" class="cursor">▌</span></template>
            </div>
            <!-- 操作条：复制按钮（豆包风格图标按钮），助手消息流式期间隐藏 -->
            <div v-if="isAssistant(m) ? (!m.streaming && (m.content || m.reasoning)) : !!m.content" class="msg-actions">
              <button
                class="action-btn"
                type="button"
                :title="m.copied === false ? '复制失败' : '复制'"
                @click="copyMessage(m)"
              >
                <svg v-if="m.copied" class="action-icon copied" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                <svg v-else class="action-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              </button>
            </div>
            <!-- 工具步骤条：放在气泡下方，避免新消息把正文顶走 -->
            <div v-if="m.tools && m.tools.length" class="tool-steps">
              <div v-for="(t, i) in m.tools" :key="i" class="tool-step">
                🐟 本喵正在叼小鱼干：<b>{{ t.name }}</b>
                <span v-if="t.done" class="tool-done">✓</span>
                <pre v-if="t.args" class="tool-args">{{ t.args }}</pre>
              </div>
            </div>
            <!-- interrupt 确认 -->
            <div v-if="m.interrupt" class="interrupt-bar">
              <div class="interrupt-title">⚠️ 需要高危操作确认，请核对以下参数：</div>
              <div v-for="(a, i) in interruptActions(m.interrupt)" :key="i" class="interrupt-action">
                <div class="interrupt-action-name">{{ a.name }}</div>
                <pre class="interrupt-action-args">{{ a.argsText }}</pre>
              </div>
              <div v-if="!interruptActions(m.interrupt).length" class="interrupt-fallback">{{ summarizeInterrupt(m.interrupt) }}</div>
              <div class="interrupt-btns">
                <button class="btn approve" @click="confirmTool(m.id, true)">允许</button>
                <button class="btn reject" @click="confirmTool(m.id, false)">拒绝</button>
              </div>
            </div>
            <div v-if="m.error" class="msg-error">{{ m.error }}</div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-bar">
        <textarea
          v-model="draft"
          class="chat-input"
          rows="2"
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          @keydown.enter.exact.prevent="submit"
        ></textarea>
        <button v-if="!generating" class="btn send" :disabled="!draft.trim()" @click="submit">发送</button>
        <button v-else class="btn stop" @click="stopGen">停止</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useAgentSocket } from '../composables/useAgentSocket'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'

const { state, connect, send, on } = useAgentSocket()

const messages = reactive([])
const draft = ref('')
const generating = ref(false)
const listRef = ref(null)
let currentMsgId = null
const unsubs = []

const connText = computed(() => ({ open: '● 已连接', connecting: '○ 连接中…', reconnecting: '○ 重连中…', closed: '○ 未连接' }[state.status] || '○ 未连接'))
const connClass = computed(() => state.status === 'open' ? 'online' : 'offline')

function scrollBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

function isAssistant(m) {
  return m.role === 'assistant'
}

// 复制助手消息：包含深度思考内容 + 正文
let copyTimer = null
async function copyMessage(m) {
  const parts = []
  if (m.reasoning) parts.push('【深度思考】\n' + m.reasoning)
  if (m.content) parts.push(m.content)
  const text = parts.join('\n\n')
  if (!text) return
  let ok = false
  try {
    await navigator.clipboard.writeText(text)
    ok = true
  } catch {
    // clipboard API 不可用时回退
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      ok = document.execCommand('copy')
      document.body.removeChild(ta)
    } catch { ok = false }
  }
  if (ok) {
    m.copied = true
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { m.copied = false }, 1500)
  } else {
    m.copied = false
    setTimeout(() => { m.copied = undefined }, 1500)
  }
}

function summarizeInterrupt(payload) {
  try {
    const actions = payload?.actions || []
    const names = actions.flatMap(a => (a?.action_requests || []).map(r => r.name))
    return names.length ? names.join(', ') : JSON.stringify(actions).slice(0, 120)
  } catch { return '未知操作' }
}

// 从 interrupt payload 提取待确认操作及其完整参数（action_requests 自带 args）
function interruptActions(payload) {
  try {
    const actions = payload?.actions || []
    return actions.flatMap(a => (a?.action_requests || []).map(r => ({
      name: r.name || '未知操作',
      argsText: r.args && Object.keys(r.args).length
        ? JSON.stringify(r.args, null, 2)
        : '(无参数)',
    })))
  } catch { return [] }
}

// 尝试美化 JSON（参数流式拼接过程中可能不完整，失败则原样展示）
function prettyArgs(raw) {
  try { return JSON.stringify(JSON.parse(raw), null, 2) } catch { return raw }
}

function submit() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  messages.push({ id: 'u-' + Date.now(), role: 'user', content: text })
  send('chat.send', { sessionId: state.sessionId, content: text })
  generating.value = true
  scrollBottom()
}

function stopGen() {
  send('chat.cancel', { sessionId: state.sessionId })
}

function confirmTool(msgId, approved) {
  const m = messages.find((x) => x.id === msgId)
  if (m) { m.interrupt = null }
  send('tool.confirm', { sessionId: state.sessionId, approved })
  generating.value = true
}

onMounted(() => {
  connect()
  // 拉取历史
  send('chat.history', { sessionId: state.sessionId, limit: 30 })
  unsubs.push(on('chat.user', (p) => {
    // 来源不是本窗口的用户消息（如桌宠发的），同步显示
    // 注意：chat.user 的 msgId 带 u- 前缀，与 chat.started 的 msgId 不同
    const existing = messages.find((m) => m.id === p.msgId || (m.role === 'user' && m.content === p.content))
    if (p.source && p.source !== 'main' && !existing) {
      messages.push({ id: p.msgId, role: 'user', content: p.content })
      scrollBottom()
    }
  }))
  unsubs.push(on('chat.started', (p) => {
    currentMsgId = p.msgId
    messages.push({ id: p.msgId, role: 'assistant', content: '', reasoning: '', reasoningOpen: true, streaming: true, thinking: false, tools: [] })
    generating.value = true
    scrollBottom()
  }))
  unsubs.push(on('chat.delta', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m) {
      // 收到正文 delta 时，标记思考阶段结束，并立即折叠深度思考区域
      if (m.thinking) {
        m.thinking = false
        m.reasoningOpen = false
      }
      m.content += p.text
      scrollBottom()
    }
  }))
  unsubs.push(on('agent.reasoning', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m) {
      m.reasoning = (m.reasoning || '') + (p.text || '')
      m.thinking = true
      scrollBottom()
    }
  }))
  unsubs.push(on('chat.completed', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m) {
      m.streaming = false
      m.thinking = false
      m.reasoningOpen = false
      // 以服务端最终全文为准（若比增量拼接更完整）
      if (p.text && p.text.length > m.content.length) m.content = p.text
    }
    generating.value = false
    scrollBottom()
  }))
  unsubs.push(on('chat.error', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m) { m.streaming = false; m.error = p.message || '生成失败' }
    generating.value = false
  }))
  unsubs.push(on('agent.tool_call', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m && p.phase === 'start') {
      m.tools.push({ name: p.name, done: false, args: '' })
      scrollBottom()
    }
  }))
  unsubs.push(on('agent.tool_args', (p) => {
    // 参数增量片段追加到最近一个进行中的工具步骤，流式展示
    const m = messages.find((x) => x.id === p.msgId)
    if (!m || !m.tools || !m.tools.length) return
    const active = [...m.tools].reverse().find((t) => !t.done)
    if (active) {
      active.args = prettyArgs((active.args || '') + (p.args || ''))
      scrollBottom()
    }
  }))
  unsubs.push(on('agent.interrupt', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m) { m.interrupt = p; m.streaming = false }
    generating.value = false
    scrollBottom()
  }))
  unsubs.push(on('chat.history.result', (p) => {
    if (messages.length === 0 && p.items && p.items.length) {
      p.items.forEach((it, i) => messages.push({
        id: 'h-' + i, role: it.role, content: it.text, reasoning: it.reasoning || '', reasoningOpen: false, thinking: false, tools: []
      }))
      scrollBottom()
    }
  }))
})

onBeforeUnmount(() => unsubs.forEach((fn) => fn()))
</script>

<style scoped>
/* 聊天区域随窗口大小自适应伸缩，不设固定宽度上限 */
.chat-page { width: 100%; height: 100%; display: flex; flex-direction: column; }
.page-header { margin-bottom: 16px; }
.page-title { font-size: 26px; font-weight: 700; color: #f1f5f9; margin-bottom: 6px; }
.page-subtitle { font-size: 14px; color: #64748b; }
.conn { margin-left: 10px; }
.conn.online { color: #34d399; }
.conn.offline { color: #f59e0b; }

.chat-card { flex: 1; display: flex; flex-direction: column; min-height: 0; background: #1e293b; border: 1px solid #334155; border-radius: 14px; overflow: hidden; }
.msg-list { flex: 1; overflow-y: auto; padding: 20px; }
.empty-hint { text-align: center; color: #64748b; margin-top: 60px; }
.empty-emoji { font-size: 44px; margin-bottom: 10px; }

.msg { display: flex; gap: 10px; margin-bottom: 16px; }
.msg.user { flex-direction: row-reverse; }
.msg-avatar { font-size: 22px; flex-shrink: 0; }
.msg-body { max-width: 76%; }
.msg-content { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 10px 14px; color: #e2e8f0; white-space: pre-wrap; word-break: break-word; line-height: 1.6; }
.msg-content.md-mode { white-space: normal; }
.msg.user .msg-content { background: #4338ca; border-color: #4f46e5; }
.cursor { animation: blink 0.8s infinite; }
@keyframes blink { 50% { opacity: 0; } }

.reasoning-block { margin-bottom: 8px; background: #0f172a; border: 1px solid #334155; border-radius: 10px; overflow: hidden; }
.reasoning-summary { cursor: pointer; padding: 8px 14px; color: #94a3b8; font-size: 13px; user-select: none; list-style: none; display: flex; align-items: center; gap: 6px; }
.reasoning-summary::-webkit-details-marker { display: none; }
.reasoning-summary::before { content: '▶'; font-size: 10px; transition: transform 0.2s; }
details[open] > .reasoning-summary::before { transform: rotate(90deg); }
.thinking-dot { color: #6366f1; animation: blink 1s infinite; margin-left: 2px; }
.reasoning-content { padding: 0 14px 10px 14px; color: #64748b; font-size: 13px; font-style: italic; white-space: pre-wrap; word-break: break-word; line-height: 1.5; border-top: 1px dashed #334155; padding-top: 8px; }

/* 消息操作条（豆包风格：无边框图标按钮，hover 浅底） */
.msg-actions { display: flex; align-items: center; justify-content: flex-end; gap: 4px; margin-top: 6px; }
.action-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border: none; border-radius: 8px;
  background: transparent; color: #64748b; cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.action-btn:hover { background: #33415580; color: #cbd5e1; }
.action-btn .action-icon { display: block; }
.action-btn .action-icon.copied { color: #34d399; }

.tool-steps { margin-top: 6px; }
.tool-step { font-size: 12px; color: #94a3b8; background: #0f172a80; border-radius: 6px; padding: 4px 10px; margin-bottom: 4px; }
.tool-done { color: #34d399; margin-left: 6px; }
.tool-args { margin: 4px 0 0; padding: 6px 8px; background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; color: #7dd3fc; font-size: 11px; font-family: Consolas, Monaco, monospace; white-space: pre-wrap; word-break: break-all; max-height: 160px; overflow-y: auto; }

.interrupt-bar { margin-top: 8px; background: #451a03; border: 1px solid #b45309; border-radius: 8px; padding: 10px 12px; color: #fbbf24; font-size: 13px; }
.interrupt-title { font-weight: 600; }
.interrupt-action { margin-top: 6px; background: #0f172a; border: 1px solid #78350f; border-radius: 6px; padding: 6px 10px; }
.interrupt-action-name { color: #fcd34d; font-weight: 600; font-size: 12px; }
.interrupt-action-args { margin: 4px 0 0; color: #7dd3fc; font-size: 12px; font-family: Consolas, Monaco, monospace; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
.interrupt-fallback { margin-top: 4px; }
.interrupt-btns { margin-top: 8px; display: flex; gap: 8px; }

.msg-error { margin-top: 6px; color: #f87171; font-size: 13px; }

.input-bar { display: flex; gap: 10px; padding: 14px; border-top: 1px solid #334155; }
.chat-input { flex: 1; resize: none; background: #0f172a; border: 1px solid #334155; border-radius: 10px; color: #e2e8f0; padding: 10px 12px; font-size: 14px; font-family: inherit; }
.chat-input:focus { outline: none; border-color: #6366f1; }
.btn { border: none; border-radius: 10px; padding: 0 22px; font-size: 14px; cursor: pointer; align-self: stretch; }
.btn.send { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; }
.btn.send:disabled { opacity: 0.4; cursor: not-allowed; }
.btn.stop { background: #7f1d1d; color: #fca5a5; }
.btn.approve { background: #065f46; color: #6ee7b7; padding: 6px 16px; }
.btn.reject { background: #7f1d1d; color: #fca5a5; padding: 6px 16px; }
</style>
