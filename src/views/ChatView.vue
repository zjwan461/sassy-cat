<template>
  <div class="page chat-page">
    <header class="page-header">
      <h1 class="page-title">唠嗑</h1>
      <p class="page-subtitle">
        与优墨对话
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
      <div class="msg-list" ref="listRef" @scroll="onMsgListScroll">
        <!-- 加载更多提示 -->
        <div v-if="chat.loadingMore" class="load-more-hint">
          <span class="spinner"></span> 加载中...
        </div>
        <div v-else-if="chat.hasMore && messages.length > 0" class="load-more-hint clickable" @click="onLoadMore">
          加载更多历史消息
        </div>
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
            <div v-if="m.content || m.images?.length || docAttachments(m).length" class="msg-content" :class="{ 'md-mode': isAssistant(m) }">
              <!-- 用户消息的图片附件 -->
              <div v-if="m.images && m.images.length" class="msg-images">
                <img v-for="(img, i) in m.images" :key="i" :src="img" class="msg-image" @click="openImagePreview(img)" />
              </div>
              <!-- 用户消息的文档附件 -->
              <div v-if="docAttachments(m).length" class="msg-doc-attachments">
                <DocumentAttachment
                  v-for="att in docAttachments(m)"
                  :key="att.id"
                  :attachment="att"
                />
              </div>
              <template v-if="isAssistant(m)">
                <MarkdownRenderer :content="m.content" :done="!m.streaming" />
              </template>
              <template v-else>{{ m.content }}</template>
            </div>
            <!-- 操作条：朗读 + 复制按钮（豆包风格图标按钮），助手消息流式期间隐藏 -->
            <div v-if="isAssistant(m) ? (!m.streaming && (m.content || m.reasoning)) : !!m.content" class="msg-actions">
              <button
                v-if="isAssistant(m) && m.content"
                class="action-btn"
                type="button"
                :class="{ speaking: isSpeaking(m) }"
                :title="isSpeaking(m) ? '停止朗读' : '朗读'"
                @click="onSpeak(m)"
              >
                <svg v-if="isSpeaking(m)" class="action-icon speaking" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" stroke="none"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>
                <svg v-else class="action-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>
              </button>
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
            <!-- 工具步骤条：放在气泡下方，避免新消息把正文顶走（默认折叠） -->
            <details v-if="m.tools && m.tools.length" class="tool-steps-wrapper">
              <summary class="tool-steps-summary">
                🛠️ 工具调用（{{ m.tools.length }}）
                <span class="tool-steps-arrow">▶</span>
              </summary>
              <div class="tool-steps">
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
            </details>
            <!-- Token 用量统计：来自 agent.usage 事件（仅助手消息，可折叠） -->
            <details v-if="isAssistant(m) && hasUsage(m.usage)" class="usage-block">
              <summary class="usage-summary">
                <span class="usage-title">⚡ Token 统计</span>
                <span class="usage-inline">{{ usageSummary(m.usage) }}</span>
                <span class="usage-arrow">▶</span>
              </summary>
              <div class="usage-body">
                <div class="usage-row">
                  <span class="usage-label">输入 tokens</span>
                  <span class="usage-value">{{ fmtTokens(m.usage.input_tokens) }}</span>
                  <span v-if="m.usage.input_token_details" class="usage-detail">
                    <span v-if="m.usage.input_token_details.cache_read != null">缓存读 {{ fmtTokens(m.usage.input_token_details.cache_read) }}</span>
                    <span v-if="m.usage.input_token_details.cache_creation != null">缓存写 {{ fmtTokens(m.usage.input_token_details.cache_creation) }}</span>
                    <span v-if="usageCacheRate(m.usage) != null" class="usage-cache-rate">命中 {{ usageCacheRate(m.usage).toFixed(1) }}%</span>
                  </span>
                </div>
                <div class="usage-row">
                  <span class="usage-label">输出 tokens</span>
                  <span class="usage-value">{{ fmtTokens(m.usage.output_tokens) }}</span>
                  <span v-if="m.usage.output_token_details" class="usage-detail">
                    <span v-if="m.usage.output_token_details.reasoning != null">推理 {{ fmtTokens(m.usage.output_token_details.reasoning) }}</span>
                    <span v-if="m.usage.output_token_details.reasoning_tokens != null">推理 {{ fmtTokens(m.usage.output_token_details.reasoning_tokens) }}</span>
                  </span>
                </div>
                <div class="usage-row usage-total">
                  <span class="usage-label">总计 tokens</span>
                  <span class="usage-value">{{ fmtTokens(m.usage.total_tokens) }}</span>
                </div>
              </div>
            </details>
            <!-- interrupt 确认（存在待确认项时自动展开；全部处理完则折叠并切换为已完成文案） -->
            <details v-if="m.interruptActions?.length" class="interrupt-bar-wrapper" :open="hasPendingDecisions(m)">
              <summary class="interrupt-bar-summary">
                {{ hasPendingDecisions(m) ? '⚠️ 需要高危操作确认，请核对参数：' : `📋 高危操作确认（已处理 ${m.interruptActions.length}/${m.interruptActions.length}）` }}
                <span class="interrupt-bar-arrow">▶</span>
              </summary>
              <div class="interrupt-bar">
                <div class="interrupt-global-btns" v-if="hasPendingDecisions(m)">
                  <button class="btn approve-all" @click="onApproveAll(m.id)">✅ 全部允许</button>
                </div>
                <div v-for="(a, i) in m.interruptActions" :key="i" class="interrupt-action" :class="getActionDecisionClass(m, i)">
                  <div class="interrupt-action-header">
                    <span class="interrupt-action-index">#{{ i + 1 }}</span>
                    <span class="interrupt-action-name">{{ a.name }}</span>
                    <span v-if="decisionType(m, i)" class="interrupt-action-status">
                      {{ decisionType(m, i) === 'approve' ? '✅ 已允许' : '❌ 已拒绝' }}
                    </span>
                  </div>
                  <pre class="interrupt-action-args">{{ a.argsText }}</pre>
                  <div v-if="!decisionType(m, i)" class="interrupt-action-btns">
                    <button class="btn-sm approve" @click="onDecision(m.id, i, 'approve')">允许</button>
                    <button class="btn-sm reject" @click="onDecision(m.id, i, 'reject')">拒绝</button>
                  </div>
                </div>
                <div v-if="!m.interruptActions?.length" class="interrupt-fallback">{{ summarizeInterrupt(m.interrupt) }}</div>
              </div>
            </details>
            <!-- 确认卡失效提示：用户在确认前发送了新消息，服务端以 respond 决策跳过挂起操作并续跑新消息 -->
            <div v-if="m.interruptExpired" class="interrupt-expired">⏹ 新消息已发送，未确认的操作已跳过</div>
            <div v-if="m.error" class="msg-error">
              <span class="msg-error-text">{{ m.error }}</span>
              <button class="msg-retry-btn" type="button" :disabled="m.streaming" @click="onRetry(m)">重试</button>
            </div>
            <!-- 光标：放在 msg-body 末尾，确保出现在所有内容（包括工具步骤和中断确认）之后 -->
            <span v-if="m.streaming" class="cursor cursor-at-end">▌</span>
          </div>
        </div>
      </div>

      <!-- 回到底部浮动按钮：用户手动上翻时出现，点击/自行滚回底部即消失 -->
      <button v-if="!stickToBottom" class="back-to-bottom" @click="onBackToBottom" title="回到底部">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
      </button>
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
          <div class="drag-hint"> 松开以上传文件</div>
        </div>
      </div>

      <!-- 消息图片放大预览弹窗 -->
      <div v-if="previewImageUrl" class="image-modal" @click="closeImagePreview">
        <img :src="previewImageUrl" class="image-modal-img" />
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '../composables/useChatStore'
import { useFileUpload } from '../composables/useFileUpload'
import { useTTS } from '../composables/useTTS'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import FilePreview from '../components/FilePreview.vue'
import DocumentAttachment from '../components/DocumentAttachment.vue'

// 会话状态与 WS 事件订阅已提升到模块级单例（useChatStore）：
// 切换 tab 导致本组件卸载时，流式数据仍在后台接收与累积；
// 重新挂载直接恢复现场继续渲染，不再出现"切走就停止渲染"的问题。
const { chat, conv, socketState, submitMessage, stopGeneration, retryLastTurn, decideInterrupt, approveAllInterrupt, newConversation, switchConversation, renameConversation, deleteConversation, loadMoreMessages } = useChatStore()
const { hasAttachments, isProcessing, handleFiles, buildAttachments, clearAllAttachments } = useFileUpload()
// 语音朗读（TTS）：播放状态（模块级，跨 tab 存活）+ 播放/停止/切换
const { speaking, playMessage, loadConfig: loadTtsConfig } = useTTS()

const messages = chat.messages
const draft = ref('')
const generating = computed(() => chat.generating)
const listRef = ref(null)
const fileInputRef = ref(null)
const isDragOver = ref(false)
const previewImageUrl = ref(null)
// 是否紧贴底部：用户手动上翻看历史时置 false（暂停自动滚动并显示浮动按钮），重新到达底部或点击按钮后恢复 true
const stickToBottom = ref(true)

// 是否已滚动到接近底部（80px 阈值内视为贴底）
function isNearBottom() {
  const el = listRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

// 强制滚动到底部并恢复自动跟随（用户主动操作：发消息/切会话/确认/点击浮动按钮）
function forceScrollBottom() {
  stickToBottom.value = true
  nextTick(() => {
    if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

function openImagePreview(url) {
  previewImageUrl.value = url
}

function closeImagePreview() {
  previewImageUrl.value = null
}

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
  forceScrollBottom()
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
    // 仅在用户未上翻时自动跟随到底部；用户手动上翻后不再强制滚动
    if (listRef.value && stickToBottom.value) listRef.value.scrollTop = listRef.value.scrollHeight
  })
}

// 浮动按钮点击：回到底部并恢复自动滚动
function onBackToBottom() {
  forceScrollBottom()
}

// 流式内容变化时自动滚动到底部（仅在本组件挂载期间生效）
watch(
  () => messages.reduce((n, m) => n + (m.content?.length || 0) + (m.reasoning?.length || 0), 0),
  scrollBottom
)

function isAssistant(m) {
  return m.role === 'assistant'
}

// ---------- 语音朗读（TTS） ----------
// 当前消息是否正在朗读（播放中按钮高亮为停止图标）
function isSpeaking(m) {
  return speaking.value === m.id
}

// 点击朗读按钮：播放/停止/切换（由 useTTS.playMessage 裁决）
function onSpeak(m) {
  if (!m.content) return
  playMessage(m.id, m.content)
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

// ---------- Token 用量统计（agent.usage） ----------
// usage_metadata 缺失部分字段（如纯缓存读、无推理 token）时只显示已有的，兼容多种模型返回
function hasUsage(u) {
  return !!u && (u.total_tokens != null || u.input_tokens != null || u.output_tokens != null)
}
function fmtTokens(n) {
  return n == null ? '0' : Number(n).toLocaleString()
}
function usageSummary(u) {
  if (!u) return ''
  const parts = []
  if (u.total_tokens != null) parts.push(`总计 ${fmtTokens(u.total_tokens)}`)
  if (u.input_tokens != null) parts.push(`输入 ${fmtTokens(u.input_tokens)}`)
  if (u.output_tokens != null) parts.push(`输出 ${fmtTokens(u.output_tokens)}`)
  return parts.join(' · ')
}

// 缓存命中率：命中读取（cache_read）的 token 占输入 token 的比例
function usageCacheRate(u) {
  if (!u) return null
  const inp = u.input_tokens
  const read = u.input_token_details?.cache_read
  if (inp == null || read == null || inp <= 0) return null
  return Math.min(100, (read / inp) * 100)
}

// 统一决策记录的形态差异：
// - 本地实时点击存的是字符串（'approve' | 'reject'）
// - 数据库历史回填的是对象（{ type: 'approve' }），且 JSON 序列化后
//   未决策项可能为 null；decisions 数组还可能短于 actions（服务端把
//   多轮 interrupt 的 actions 累积到同一条消息，decisions 只含已确认部分）
function decisionType(m, i) {
  const d = m.interruptDecisions?.[i]
  if (!d) return null
  return (typeof d === 'string' ? d : d.type) || null
}

// 判断消息是否还有未确认的操作（以 actions 长度为基准逐项检查，
// 避免 decisions 数组偏短时漏判新增的待确认项）
function hasPendingDecisions(m) {
  if (!m.interruptActions || !m.interruptActions.length) return false
  return m.interruptActions.some((_, i) => !decisionType(m, i))
}

// 获取操作的样式类（已允许/已拒绝/待确认）
function getActionDecisionClass(m, i) {
  const t = decisionType(m, i)
  if (t === 'approve') return 'action-approved'
  if (t === 'reject') return 'action-rejected'
  return 'action-pending'
}

// 单个操作的确认/拒绝
function onDecision(msgId, index, decision) {
  decideInterrupt(msgId, index, decision)
  forceScrollBottom()
}

// 全部允许
function onApproveAll(msgId) {
  approveAllInterrupt(msgId)
  forceScrollBottom()
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
  forceScrollBottom()
}

function stopGen() {
  stopGeneration()
}

// 重试上一轮失败的生成（是否重试由用户决定）；重试后滚到底部跟随新内容
function onRetry(m) {
  retryLastTurn(m.id)
  forceScrollBottom()
}

// ---------- 文档附件提取 ----------
function docAttachments(m) {
  if (!m.attachments) return []
  return m.attachments.filter(a => a.type === 'document')
}

// ---------- 滚动加载更多历史消息 ----------
function onMsgListScroll() {
  if (!listRef.value) return
  const { scrollTop } = listRef.value
  // 当滚动到顶部附近（50px 以内）时触发加载
  if (scrollTop < 50 && chat.hasMore && !chat.loadingMore) {
    onLoadMore()
  }
  // 同步"是否贴底"状态：用户手动上翻 → 暂停自动跟随并显示浮动按钮；滚回底部 → 恢复自动跟随
  stickToBottom.value = isNearBottom()
}

async function onLoadMore() {
  if (chat.loadingMore || !chat.hasMore) return
  const oldScrollHeight = listRef.value?.scrollHeight || 0
  await loadMoreMessages()
  // 保持滚动位置：新消息插入头部后，调整 scrollTop 使当前内容不跳动
  await nextTick()
  if (listRef.value) {
    const newScrollHeight = listRef.value.scrollHeight
    const diff = newScrollHeight - oldScrollHeight
    if (diff > 0) {
      listRef.value.scrollTop += diff
    }
  }
}

onMounted(() => {
  // 回到页面时若仍处于流式轮次，恢复滚动位置（进入页面默认贴底并恢复自动跟随）
  forceScrollBottom()
  // 刷新语音配置（用户在设置页可能改过自动朗读/语音等，回到聊天页即时生效）
  loadTtsConfig()
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
.chat-body { flex: 1; min-height: 0; display: flex; flex-direction: row; position: relative; }

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

.msg-list { flex: 1; overflow-y: auto; padding: 16px 20px; padding-bottom: 100px; }
.empty-hint { text-align: center; color: #64748b; margin-top: 60px; }
.empty-emoji { font-size: 44px; margin-bottom: 10px; }

/* 加载更多提示 */
.load-more-hint { text-align: center; color: #64748b; font-size: 13px; padding: 12px 0; display: flex; align-items: center; justify-content: center; gap: 8px; }
.load-more-hint.clickable { cursor: pointer; transition: color 0.15s; }
.load-more-hint.clickable:hover { color: #94a3b8; }
.load-more-hint .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #64748b; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 文档附件区域 */
.msg-doc-attachments { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }

.msg { display: flex; gap: 10px; margin-bottom: 12px; }
.msg.user { flex-direction: row-reverse; }
.msg-avatar { font-size: 22px; flex-shrink: 0; }
.msg-body { max-width: 76%; }
.msg-content { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 10px 14px; color: #e2e8f0; white-space: pre-wrap; word-break: break-word; line-height: 1.6; }
.msg-content.md-mode { white-space: normal; }
.msg.user .msg-content { background: #4338ca; border-color: #4f46e5; }
.cursor { animation: blink 0.8s infinite; }
.cursor-at-end { display: inline-block; margin-left: 4px; vertical-align: middle; }
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
.action-btn.speaking { color: #34d399; }
.action-btn.speaking .action-icon { color: #34d399; }

/* 工具调用折叠容器 */
.tool-steps-wrapper { margin-top: 6px; background: #0f172a80; border: 1px solid #334155; border-radius: 8px; overflow: hidden; }
.tool-steps-summary { cursor: pointer; padding: 6px 12px; color: #94a3b8; font-size: 13px; user-select: none; list-style: none; display: flex; align-items: center; justify-content: space-between; transition: background 0.15s; }
.tool-steps-summary::-webkit-details-marker { display: none; }
.tool-steps-summary:hover { background: #1e293b; }
.tool-steps-arrow { font-size: 10px; transition: transform 0.2s; }
.tool-steps-wrapper[open] > .tool-steps-summary .tool-steps-arrow { transform: rotate(90deg); }
.tool-steps { padding: 0 8px 8px 8px; }
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

/* Token 用量统计折叠容器 */
.usage-block { margin-top: 6px; background: #0f172a80; border: 1px solid #334155; border-radius: 8px; overflow: hidden; }
.usage-summary { cursor: pointer; padding: 6px 12px; color: #94a3b8; font-size: 12px; user-select: none; list-style: none; display: flex; align-items: center; gap: 8px; transition: background 0.15s; }
.usage-summary::-webkit-details-marker { display: none; }
.usage-summary:hover { background: #1e293b; }
.usage-arrow { font-size: 10px; transition: transform 0.2s; color: #64748b; }
.usage-block[open] > .usage-summary .usage-arrow { transform: rotate(90deg); }
.usage-inline { color: #34d399; font-size: 11px; margin-left: auto; }
.usage-body { padding: 0 12px 10px 12px; display: flex; flex-direction: column; gap: 4px; }
.usage-row { display: flex; align-items: baseline; gap: 8px; font-size: 12px; color: #94a3b8; }
.usage-label { color: #64748b; min-width: 76px; }
.usage-value { color: #e2e8f0; font-family: Consolas, Monaco, monospace; font-weight: 600; }
.usage-detail { color: #64748b; font-size: 11px; display: flex; gap: 10px; }
.usage-cache-rate { color: #34d399; font-weight: 600; }
.usage-total { border-top: 1px dashed #334155; padding-top: 6px; margin-top: 2px; }
.usage-total .usage-value { color: #34d399; }

/* 高危操作确认折叠容器 */
.interrupt-bar-wrapper { margin-top: 8px; background: #0f172a80; border: 1px solid #b45309; border-radius: 8px; overflow: hidden; }
.interrupt-bar-summary { cursor: pointer; padding: 8px 12px; color: #fbbf24; font-size: 13px; font-weight: 600; user-select: none; list-style: none; display: flex; align-items: center; justify-content: space-between; transition: background 0.15s; }
.interrupt-bar-summary::-webkit-details-marker { display: none; }
.interrupt-bar-summary:hover { background: #451a03; }
.interrupt-bar-arrow { font-size: 10px; transition: transform 0.2s; }
.interrupt-bar-wrapper[open] > .interrupt-bar-summary .interrupt-bar-arrow { transform: rotate(90deg); }
.interrupt-bar { background: #451a03; border: none; border-radius: 0; padding: 10px 12px; color: #fbbf24; font-size: 13px; }
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

.msg-error { display: flex; align-items: center; gap: 10px; margin-top: 6px; color: #f87171; font-size: 13px; }
.msg-error-text { flex: 1; min-width: 0; }
.msg-retry-btn {
  flex-shrink: 0;
  padding: 4px 14px;
  font-size: 12px;
  color: #f87171;
  background: rgba(248, 113, 113, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.4);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.msg-retry-btn:hover:not(:disabled) { background: rgba(248, 113, 113, 0.22); border-color: rgba(248, 113, 113, 0.7); }
.msg-retry-btn:disabled { opacity: 0.5; cursor: default; }

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
  width: 38px;
  height: 38px;
  padding: 0;
  font-size: 20px;
  background: #334155;
  color: #e2e8f0;
  transition: background 0.15s, color 0.15s;
  align-self: flex-start;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 6px;
}
.attach-btn:hover { background: #475569; color: #fff; }
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

/* 消息图片放大预览弹窗 */
.image-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  cursor: pointer;
}
.image-modal-img {
  max-width: 90%;
  max-height: 90%;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  cursor: default;
}

/* 回到底部浮动按钮：用户手动上翻时出现，点击/自行滚回底部即消失 */
.back-to-bottom {
  position: absolute;
  right: 28px;
  bottom: 20px;
  width: 38px;
  height: 38px;
  border: none;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
  transition: transform 0.15s, filter 0.15s;
  z-index: 5;
}
.back-to-bottom:hover { transform: translateY(-2px); filter: brightness(1.1); }
.back-to-bottom:active { transform: translateY(0); }
</style>
