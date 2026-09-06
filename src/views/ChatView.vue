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
            <!-- 工具步骤条 -->
            <div v-if="m.tools && m.tools.length" class="tool-steps">
              <div v-for="(t, i) in m.tools" :key="i" class="tool-step">
                🔧 本喵正在使用工具：<b>{{ t.name }}</b>
                <span v-if="t.done" class="tool-done">✓</span>
              </div>
            </div>
            <div class="msg-content">{{ m.content }}<span v-if="m.streaming" class="cursor">▌</span></div>
            <!-- interrupt 确认 -->
            <div v-if="m.interrupt" class="interrupt-bar">
              <span>⚠️ 需要高危操作确认：{{ summarizeInterrupt(m.interrupt) }}</span>
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

function summarizeInterrupt(payload) {
  try {
    const actions = payload?.actions || []
    const names = actions.flatMap(a => (a?.action_requests || []).map(r => r.name))
    return names.length ? names.join(', ') : JSON.stringify(actions).slice(0, 120)
  } catch { return '未知操作' }
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
    messages.push({ id: p.msgId, role: 'assistant', content: '', streaming: true, tools: [] })
    generating.value = true
    scrollBottom()
  }))
  unsubs.push(on('chat.delta', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m) { m.content += p.text; scrollBottom() }
  }))
  unsubs.push(on('chat.completed', (p) => {
    const m = messages.find((x) => x.id === p.msgId)
    if (m) {
      m.streaming = false
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
      m.tools.push({ name: p.name, done: false })
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
        id: 'h-' + i, role: it.role, content: it.text, tools: []
      }))
      scrollBottom()
    }
  }))
})

onBeforeUnmount(() => unsubs.forEach((fn) => fn()))
</script>

<style scoped>
.chat-page { max-width: 900px; height: 100%; display: flex; flex-direction: column; }
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
.msg.user .msg-content { background: #4338ca; border-color: #4f46e5; }
.cursor { animation: blink 0.8s infinite; }
@keyframes blink { 50% { opacity: 0; } }

.tool-steps { margin-bottom: 6px; }
.tool-step { font-size: 12px; color: #94a3b8; background: #0f172a80; border-radius: 6px; padding: 4px 10px; margin-bottom: 4px; }
.tool-done { color: #34d399; margin-left: 6px; }

.interrupt-bar { margin-top: 8px; background: #451a03; border: 1px solid #b45309; border-radius: 8px; padding: 10px 12px; color: #fbbf24; font-size: 13px; }
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
