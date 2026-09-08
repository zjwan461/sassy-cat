<template>
  <div class="page chat-page">
    <header class="page-header">
      <h1 class="page-title">AI 聊天</h1>
      <p class="page-subtitle">
        与臭屁猫对话
        <span class="conn" :class="connClass">{{ connText }}</span>
      </p>
    </header>
    <!-- 紧凑单行页头：标题与状态同行，把纵向空间让给聊天区 -->

    <section class="card chat-card">
      <!-- 上半区：会话侧栏 + 消息流并排 -->
      <div class="chat-body">
      <!-- 会话侧栏：历史对话列表 + 新建 -->
      <aside class="conv-panel">
        <button class="btn conv-new" @click="onNewConv">＋ 新建对话</button>
        <div class="conv-list">
          <div
            v-for="c in conv.list"
            :key="c.id"
            class="conv-item"
            :class="{ active: c.id === chat.convId }"
            @click="onSwitchConv(c)"
          >
            <template v-if="editingId === c.id">
              <input
                ref="renameInputRef"
                v-model="editingTitle"
                class="conv-rename-input"
                @keydown.enter.prevent="commitRename(c)"
                @keydown.esc="cancelRename"
                @blur="commitRename(c)"
                @click.stop
              />
            </template>
            <template v-else>
              <div class="conv-item-main">
                <div class="conv-title">{{ c.title || '新对话' }}</div>
                <div class="conv-time">{{ relTime(c.updatedAt) }}</div>
              </div>
              <div class="conv-actions">
                <button class="conv-action-btn" title="重命名" @click.stop="startRename(c)">✎</button>
                <button class="conv-action-btn del" title="删除" @click.stop="onDeleteConv(c)">🗑</button>
              </div>
            </template>
          </div>
          <div v-if="!conv.list.length" class="conv-empty">还没有对话</div>
        </div>
      </aside>

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
              <!-- 用户消息的图片附件 -->
              <div v-if="m.images && m.images.length" class="msg-images">
                <img v-for="(img, i) in m.images" :key="i" :src="img" class="msg-image" />
              </div>
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
                <span v-if="t.done" class="tool-done" :class="{ failed: t.status === 'error' }">{{ t.status === 'error' ? '✕' : '✓' }}</span>
                <pre v-if="t.args" class="tool-args">{{ t.args }}</pre>
                <!-- 历史回填的工具结果（实时流无 result 字段，自然不显示） -->
                <details v-if="t.result" class="tool-result">
                  <summary class="tool-result-summary">执行结果</summary>
                  <pre class="tool-result-body">{{ t.result }}</pre>
                </details>
              </div>
            </div>
            <!-- interrupt 确认 -->
            <div v-if="m.interruptActions?.length" class="interrupt-bar">
              <div class="interrupt-title">⚠️ 需要高危操作确认，请核对以下参数：</div>
              <div class="interrupt-global-btns" v-if="hasPendingDecisions(m)">
                <button class="btn approve-all" @click="onApproveAll(m.id)">✅ 全部允许</button>
              </div>
              <div v-for="(a, i) in m.interruptActions" :key="i" class="interrupt-action" :class="getActionDecisionClass(m, i)">
                <div class="interrupt-action-header">
                  <span class="interrupt-action-index">#{{ i + 1 }}</span>
                  <span class="interrupt-action-name">{{ a.name }}</span>
                  <span v-if="m.interruptDecisions?.[i]" class="interrupt-action-status">
                    {{ m.interruptDecisions[i] === 'approve' ? '✅ 已允许' : '❌ 已拒绝' }}
                  </span>
                </div>
                <pre class="interrupt-action-args">{{ a.argsText }}</pre>
                <div v-if="m.interruptDecisions?.[i] === undefined" class="interrupt-action-btns">
                  <button class="btn-sm approve" @click="onDecision(m.id, i, 'approve')">允许</button>
                  <button class="btn-sm reject" @click="onDecision(m.id, i, 'reject')">拒绝</button>
                </div>
              </div>
              <div v-if="!m.interruptActions?.length" class="interrupt-fallback">{{ summarizeInterrupt(m.interrupt) }}</div>
            </div>
            <!-- 确认卡失效提示：用户在确认前发送了新消息，服务端以 respond 决策跳过挂起操作并续跑新消息 -->
            <div v-if="m.interruptExpired" class="interrupt-expired">⏹ 新消息已发送，未确认的操作已跳过</div>
            <div v-if="m.error" class="msg-error">{{ m.error }}</div>
          </div>
        </div>
      </div>
      </div>

      <!-- 输入区：永远固定在卡片最底部，横跨整宽 -->
      <div 
        class="input-area"
        :class="{ 'drag-over': isDragOver }"
        @dragover.prevent="onDragOver"
        @dragleave="onDragLeave"
        @drop.prevent="onDrop"
      >
        <!-- 文件预览区 -->
        <FilePreview v-if="hasAttachments" />
        
        <div class="input-bar">
          <button class="btn attach-btn" @click="triggerFileInput" title="上传图片或文件">📎</button>
          <input 
            ref="fileInputRef"
            type="file" 
            multiple 
            style="display: none"
            @change="onFileSelect"
          />
          <textarea
            v-model="draft"
            class="chat-input"
            rows="2"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行，可粘贴/拖拽图片"
            @keydown.enter.exact.prevent="submit"
            @paste="onPaste"
          ></textarea>
          <button v-if="!generating" class="btn send" :disabled="(!draft.trim() && !hasAttachments) || isProcessing" @click="submit">发送</button>
          <button v-else class="btn stop" @click="stopGen">停止</button>
        </div>
        
        <!-- 拖拽提示遮罩 -->
        <div v-if="isDragOver" class="drag-overlay">
          <div class="drag-hint">📁 松开以上传文件</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useChatStore } from '../composables/useChatStore'
import { useFileUpload } from '../composables/useFileUpload'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import FilePreview from '../components/FilePreview.vue'

// 会话状态与 WS 事件订阅已提升到模块级单例（useChatStore）：
// 切换 tab 导致本组件卸载时，流式数据仍在后台接收与累积；
// 重新挂载直接恢复现场继续渲染，不再出现"切走就停止渲染"的问题。
const { chat, conv, socketState, submitMessage, stopGeneration, decideInterrupt, approveAllInterrupt, newConversation, switchConversation, renameConversation, deleteConversation } = useChatStore()
const { hasAttachments, isProcessing, handleFiles, buildAttachments, clearAllAttachments } = useFileUpload()

const messages = chat.messages
const draft = ref('')
const generating = computed(() => chat.generating)
const listRef = ref(null)
const fileInputRef = ref(null)
const isDragOver = ref(false)

// ---------- 会话侧栏 ----------
const editingId = ref(null)
const editingTitle = ref('')
const renameInputRef = ref(null)

function relTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - ts
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.floor(h / 24)
  if (d < 7) return `${d} 天前`
  return new Date(ts).toLocaleDateString('zh-CN')
}

function onNewConv() {
  newConversation()
}

function onSwitchConv(c) {
  if (c.id === chat.convId) return
  switchConversation(c.id)
  scrollBottom()
}

function startRename(c) {
  editingId.value = c.id
  editingTitle.value = c.title || ''
  nextTick(() => {
    const el = Array.isArray(renameInputRef.value) ? renameInputRef.value[0] : renameInputRef.value
    el && el.focus()
  })
}

function cancelRename() {
  editingId.value = null
  editingTitle.value = ''
}

function commitRename(c) {
  if (editingId.value !== c.id) return
  const title = editingTitle.value.trim()
  editingId.value = null
  if (title && title !== c.title) renameConversation(c.id, title)
}

function onDeleteConv(c) {
  if (!window.confirm(`删除对话「${c.title || '新对话'}」？消息记录仍会保留在本地。`)) return
  deleteConversation(c.id)
}

const connText = computed(() => ({ open: '● 已连接', connecting: '○ 连接中…', reconnecting: '○ 重连中…', closed: '○ 未连接' }[socketState.status] || '○ 未连接'))
const connClass = computed(() => socketState.status === 'open' ? 'online' : 'offline')

function scrollBottom() {
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

// 流式内容变化时自动滚动到底部（仅在本组件挂载期间生效）
watch(
  () => messages.reduce((n, m) => n + (m.content?.length || 0) + (m.reasoning?.length || 0), 0),
  scrollBottom
)

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

// 判断消息是否还有未确认的操作
function hasPendingDecisions(m) {
  if (!m.interruptDecisions || !m.interruptActions) return false
  return m.interruptDecisions.some((d, i) => d === undefined && i < m.interruptActions.length)
}

// 获取操作的样式类（已允许/已拒绝/待确认）
function getActionDecisionClass(m, i) {
  if (m.interruptDecisions?.[i] === 'approve') return 'action-approved'
  if (m.interruptDecisions?.[i] === 'reject') return 'action-rejected'
  return 'action-pending'
}

// 单个操作的确认/拒绝
function onDecision(msgId, index, decision) {
  decideInterrupt(msgId, index, decision)
  scrollBottom()
}

// 全部允许
function onApproveAll(msgId) {
  approveAllInterrupt(msgId)
  scrollBottom()
}

// ---------- 文件上传相关 ----------
function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileSelect(e) {
  const files = e.target.files
  if (files && files.length) {
    handleFiles(Array.from(files))
  }
  // 清空 input 值，允许重复选择同一文件
  e.target.value = ''
}

function onDragOver(e) {
  isDragOver.value = true
}

function onDragLeave(e) {
  // 只有当离开目标元素时才隐藏（避免子元素触发）
  if (e.currentTarget === e.target) {
    isDragOver.value = false
  }
}

function onDrop(e) {
  isDragOver.value = false
  const files = e.dataTransfer?.files
  if (files && files.length) {
    handleFiles(Array.from(files))
  }
}

function onPaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  
  const files = []
  for (const item of items) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  
  if (files.length) {
    e.preventDefault()
    handleFiles(files)
  }
}

function submit() {
  const text = draft.value.trim()
  const attachments = buildAttachments()
  
  // 没有文本也没有附件时不发送
  if (!text && !attachments.length) return
  
  draft.value = ''
  submitMessage(text, attachments)
  clearAllAttachments()
  scrollBottom()
}

function stopGen() {
  stopGeneration()
}

onMounted(() => {
  // 回到页面时若仍处于流式轮次，恢复滚动位置
  scrollBottom()
})
</script>

<style scoped>
/* 聊天区域随窗口大小自适应伸缩，不设固定宽度上限 */
.chat-page { width: 100%; height: 100%; display: flex; flex-direction: column; }
/* 紧凑单行页头 */
.page-header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
.page-title { font-size: 18px; font-weight: 700; color: #f1f5f9; margin: 0; }
.page-subtitle { font-size: 12px; color: #64748b; margin: 0; }
.conn { margin-left: 8px; }
.conn.online { color: #34d399; }
.conn.offline { color: #f59e0b; }

/* 卡片纵向：上半区（侧栏+消息流并排）+ 底部全宽输入区 */
.chat-card { flex: 1; display: flex; flex-direction: column; min-height: 0; background: #1e293b; border: 1px solid #334155; border-radius: 14px; overflow: hidden; }
.chat-body { flex: 1; min-height: 0; display: flex; flex-direction: row; }

/* ===== 会话侧栏（紧凑） ===== */
.conv-panel { width: 176px; min-width: 176px; display: flex; flex-direction: column; border-right: 1px solid #334155; background: #172033; padding: 8px; gap: 6px; }
.conv-new { width: 100%; height: 32px; align-self: auto; flex-shrink: 0; font-size: 13px; background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; font-weight: 600; }
.conv-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.conv-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 8px; cursor: pointer; transition: background 0.15s; }
.conv-item:hover { background: #273449; }
.conv-item.active { background: #4f46e533; outline: 1px solid #6366f1; }
.conv-item-main { flex: 1; min-width: 0; }
.conv-title { font-size: 12.5px; color: #e2e8f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-time { font-size: 10px; color: #64748b; margin-top: 1px; }
.conv-actions { display: none; flex-shrink: 0; gap: 2px; }
.conv-item:hover .conv-actions { display: flex; }
.conv-action-btn { border: none; background: transparent; color: #94a3b8; cursor: pointer; font-size: 12px; padding: 4px; border-radius: 4px; }
.conv-action-btn:hover { background: #334155; color: #e2e8f0; }
.conv-action-btn.del:hover { color: #f87171; }
.conv-rename-input { flex: 1; min-width: 0; background: #0f172a; border: 1px solid #6366f1; border-radius: 6px; color: #e2e8f0; padding: 4px 8px; font-size: 13px; font-family: inherit; }
.conv-rename-input:focus { outline: none; }
.conv-empty { text-align: center; color: #64748b; font-size: 13px; margin-top: 20px; }
/* 窄屏折叠侧栏 */
@media (max-width: 900px) {
  .conv-panel { width: 48px; min-width: 48px; padding: 8px 4px; }
  .conv-panel .conv-new { font-size: 0; padding: 0; }
  .conv-panel .conv-new::before { content: '＋'; font-size: 18px; }
  .conv-item-main, .conv-actions { display: none; }
  .conv-item::before { content: '💬'; font-size: 14px; }
}

.msg-list { flex: 1; overflow-y: auto; padding: 16px 20px; }
.empty-hint { text-align: center; color: #64748b; margin-top: 60px; }
.empty-emoji { font-size: 44px; margin-bottom: 10px; }

.msg { display: flex; gap: 10px; margin-bottom: 12px; }
.msg.user { flex-direction: row-reverse; }
.msg-avatar { font-size: 22px; flex-shrink: 0; }
.msg-body { max-width: 76%; }
.msg-content { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 10px 14px; color: #e2e8f0; white-space: pre-wrap; word-break: break-word; line-height: 1.6; }
.msg-content.md-mode { white-space: normal; }
.msg.user .msg-content { background: #4338ca; border-color: #4f46e5; }
.cursor { animation: blink 0.8s infinite; }
@keyframes blink { 50% { opacity: 0; } }

/* 用户消息中的图片 */
.msg-images { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.msg-image { max-width: 200px; max-height: 200px; border-radius: 8px; border: 1px solid #334155; cursor: pointer; }

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
.tool-done.failed { color: #f87171; }
.tool-result { margin-top: 4px; }
.tool-result-summary { cursor: pointer; color: #64748b; font-size: 11px; user-select: none; list-style: none; }
.tool-result-summary::-webkit-details-marker { display: none; }
.tool-result-summary::before { content: '▶'; font-size: 9px; margin-right: 4px; display: inline-block; transition: transform 0.2s; }
.tool-result[open] > .tool-result-summary::before { transform: rotate(90deg); }
.tool-result-body { margin: 4px 0 0; padding: 6px 8px; background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; color: #94a3b8; font-size: 11px; font-family: Consolas, Monaco, monospace; white-space: pre-wrap; word-break: break-all; max-height: 160px; overflow-y: auto; }
.tool-args { margin: 4px 0 0; padding: 6px 8px; background: #0f172a; border: 1px solid #1e293b; border-radius: 6px; color: #7dd3fc; font-size: 11px; font-family: Consolas, Monaco, monospace; white-space: pre-wrap; word-break: break-all; max-height: 160px; overflow-y: auto; }

.interrupt-bar { margin-top: 8px; background: #451a03; border: 1px solid #b45309; border-radius: 8px; padding: 10px 12px; color: #fbbf24; font-size: 13px; }
.interrupt-title { font-weight: 600; margin-bottom: 8px; }
.interrupt-global-btns { margin-bottom: 10px; display: flex; gap: 8px; }
.btn.approve-all { background: #065f46; color: #6ee7b7; padding: 6px 16px; font-weight: 600; }
.interrupt-action { margin-top: 6px; background: #0f172a; border: 1px solid #78350f; border-radius: 6px; padding: 6px 10px; transition: border-color 0.2s, opacity 0.2s; }
.interrupt-action.action-approved { border-color: #059669; opacity: 0.85; }
.interrupt-action.action-rejected { border-color: #dc2626; opacity: 0.7; }
.interrupt-action-header { display: flex; align-items: center; gap: 6px; }
.interrupt-action-index { color: #94a3b8; font-size: 11px; font-weight: 600; }
.interrupt-action-name { color: #fcd34d; font-weight: 600; font-size: 12px; }
.interrupt-action-status { margin-left: auto; font-size: 12px; }
.interrupt-action-args { margin: 4px 0 0; color: #7dd3fc; font-size: 12px; font-family: Consolas, Monaco, monospace; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
.interrupt-action-btns { margin-top: 6px; display: flex; gap: 6px; }
.interrupt-fallback { margin-top: 4px; }
.interrupt-expired { margin-top: 8px; padding: 6px 12px; background: #1e293b; border: 1px dashed #475569; border-radius: 8px; color: #64748b; font-size: 12px; }
.interrupt-btns { margin-top: 8px; display: flex; gap: 8px; }
.btn-sm { border: none; border-radius: 6px; padding: 4px 12px; font-size: 12px; cursor: pointer; }
.btn-sm.approve { background: #065f46; color: #6ee7b7; }
.btn-sm.reject { background: #7f1d1d; color: #fca5a5; }

.msg-error { margin-top: 6px; color: #f87171; font-size: 13px; }

/* 输入区域 */
.input-area { 
  position: relative; 
  border-top: 1px solid #334155; 
  flex-shrink: 0;
  transition: border-color 0.2s;
}
.input-area.drag-over { 
  border-color: #6366f1;
  background: rgba(99, 102, 241, 0.05);
}
.input-bar { display: flex; gap: 10px; padding: 10px 14px; flex-shrink: 0; }
.attach-btn { 
  flex-shrink: 0; 
  width: 36px; 
  padding: 0; 
  font-size: 18px;
  background: #334155;
  transition: background 0.15s;
}
.attach-btn:hover { background: #475569; }
.chat-input { flex: 1; resize: none; background: #0f172a; border: 1px solid #334155; border-radius: 10px; color: #e2e8f0; padding: 8px 12px; font-size: 14px; font-family: inherit; }
.chat-input:focus { outline: none; border-color: #6366f1; }

/* 拖拽遮罩 */
.drag-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(99, 102, 241, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 10;
}
.drag-hint {
  background: #6366f1;
  color: #fff;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
}

.btn { border: none; border-radius: 10px; padding: 0 18px; font-size: 14px; cursor: pointer; align-self: stretch; }
.btn.send { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; }
.btn.send:disabled { opacity: 0.4; cursor: not-allowed; }
.btn.stop { background: #7f1d1d; color: #fca5a5; }
.btn.approve { background: #065f46; color: #6ee7b7; padding: 6px 16px; }
.btn.reject { background: #7f1d1d; color: #fca5a5; padding: 6px 16px; }
</style>
