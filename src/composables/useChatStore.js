/**
 * 聊天会话状态（模块级单例）
 *
 * 消息列表、轮次状态以及所有 WebSocket 事件订阅都挂在模块作用域，
 * 与 ChatView 组件的挂载/卸载解耦：切换 tab 时组件销毁也不会停止
 * 流式渲染数据的接收与累积，切回来直接恢复现场继续渲染。
 */
import { reactive } from 'vue'
import { useAgentSocket } from './useAgentSocket'

const { state: socketState, connect, send, on } = useAgentSocket()

export const chat = reactive({
  messages: [],
  generating: false,
  // 当前会话（对话）：id 即 LangGraph thread_id，由服务端激活会话下发
  convId: null,
  convTitle: ''
})

// 会话列表（元数据来自服务端 conversations.json，按 updatedAt 倒序）
export const conv = reactive({
  list: [],
  loading: false
})

let currentMsgId = null
let started = false // 幂等守卫：事件订阅只注册一次

// 尝试美化 JSON（参数流式拼接过程中可能不完整，失败则原样展示）
function prettyArgs(raw) {
  try { return JSON.stringify(JSON.parse(raw), null, 2) } catch { return raw }
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

// 使所有待确认的 interrupt 卡失效：新消息发送时，服务端会把新消息作为
// respond 决策消费掉挂起的 interrupt 并直接续跑，旧确认卡若仍可点击，
// 点下去会触发无效的 tool.confirm，造成消息错乱
function expirePendingInterrupts() {
  for (const m of chat.messages) {
    if (m.interruptActions?.length) {
      m.interruptActions = null
      m.interruptDecisions = null
      m.interrupt = null
      m.interruptExpired = true
    }
  }
}

/** 模块初始化：注册一次全局事件订阅（与组件生命周期无关） */
function ensureStarted() {
  if (started) return
  started = true
  connect()

  on('chat.user', (p) => {
    // 来源不是本窗口的用户消息（如桌宠发的），同步显示
    // 注意：chat.user 的 msgId 带 u- 前缀，与 chat.started 的 msgId 不同
    const existing = chat.messages.find((m) => m.id === p.msgId || (m.role === 'user' && m.content === p.content))
    if (p.source && p.source !== 'main' && !existing) {
      chat.messages.push({ id: p.msgId, role: 'user', content: p.content })
    }
  })
  on('chat.started', (p) => {
    currentMsgId = p.msgId
    chat.messages.push({ id: p.msgId, role: 'assistant', content: '', reasoning: '', reasoningOpen: true, streaming: true, thinking: false, tools: [] })
    chat.generating = true
  })
  on('chat.delta', (p) => {
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (m) {
      // 收到正文 delta 时，标记思考阶段结束，并立即折叠深度思考区域
      if (m.thinking) {
        m.thinking = false
        m.reasoningOpen = false
      }
      m.content += p.text
    }
  })
  on('agent.reasoning', (p) => {
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (m) {
      m.reasoning = (m.reasoning || '') + (p.text || '')
      // 正文守卫：一旦消息已开始输出正文，reasoning 只静默追加，不再点亮"思考中"或展开思考区
      if (!m.content) {
        m.thinking = true
      } else {
        m.thinking = false
        m.reasoningOpen = false
      }
    }
  })
  on('chat.completed', (p) => {
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (m) {
      m.streaming = false
      m.thinking = false
      m.reasoningOpen = false
      // 以服务端最终全文为准（若比增量拼接更完整）
      if (p.text && p.text.length > m.content.length) m.content = p.text
    }
    // 仅当前轮次的完成才复位 generating：旧轮次迟到的 completed 不得打断新轮次
    if (p.msgId === currentMsgId) chat.generating = false
  })
  on('chat.error', (p) => {
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (m) { m.streaming = false; m.error = p.message || '生成失败' }
    if (p.msgId === currentMsgId) chat.generating = false
  })
  on('agent.tool_call', (p) => {
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (m && p.phase === 'start') {
      m.tools.push({ name: p.name, done: false, args: '' })
    }
  })
  on('agent.tool_args', (p) => {
    // 参数增量片段追加到最近一个进行中的工具步骤，流式展示
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (!m || !m.tools || !m.tools.length) return
    const active = [...m.tools].reverse().find((t) => !t.done)
    if (active) {
      active.args = prettyArgs((active.args || '') + (p.args || ''))
    }
  })
  on('agent.interrupt', (p) => {
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (m) {
      m.interrupt = p
      m.interruptActions = interruptActions(p)
      m.interruptDecisions = new Array(m.interruptActions.length).fill(undefined)
      m.streaming = false
    }
    if (p.msgId === currentMsgId) chat.generating = false
  })
  // 服务端判定确认卡已失效（resume 时线程已不再挂起）：置灰所有待确认卡。
  // 若此刻并无轮次在流式输出，说明本次 confirm 被拒绝且不会有后续轮次，
  // 复位 generating，避免停止按钮永久卡住。
  on('agent.interrupt.expired', () => {
    expirePendingInterrupts()
    if (!chat.messages.some((m) => m.streaming)) chat.generating = false
  })
  on('chat.history.result', (p) => {
    // 只回填当前激活会话的历史：切会话后旧请求的迟到响应直接丢弃
    if (p.sessionId && chat.convId && p.sessionId !== chat.convId) return
    // 仅在尚无本地消息时回填历史；若切走期间有轮次在流式累积，
    // messages 非空则跳过，避免覆盖实时状态
    if (chat.messages.length === 0 && p.items && p.items.length) {
      p.items.forEach((it, i) => chat.messages.push({
        id: 'h-' + i, role: it.role, content: it.text, reasoning: it.reasoning || '', reasoningOpen: false, thinking: false,
        // 历史工具条目结构对齐实时流 { name, done, args }，额外带 result/status 供折叠查看
        tools: (it.tools || []).map((t) => ({ name: t.name, done: !!t.done, status: t.status, args: prettyArgs(t.args || ''), result: t.result || '' }))
      }))
    }
  })

  // ---------- 会话管理事件 ----------
  // 首次连通（或重连）时对齐激活会话：进入页面早于 WS 连上的场景，
  // 由 connected 帧驱动补拉会话列表与历史
  on('connected', (p) => {
    if (!p.sessionId) return
    loadConversations()
    // 已对齐同一会话（常规重连）：现场保持不动
    if (chat.convId === p.sessionId) return
    // 服务端激活会话与本地现场不同（断线期间其他窗口切换/首次进入）：
    // 丢弃旧会话现场，按新激活会话重建
    chat.convId = p.sessionId
    chat.messages.splice(0, chat.messages.length)
    chat.generating = false
    send('chat.history', { sessionId: p.sessionId, limit: 30 })
  })
  on('conv.list.result', (p) => {
    conv.list = p.items || []
    conv.loading = false
  })
  // 激活会话变更（新建/切换/删除回退，含其他窗口触发）：
  // 清空现场并重新拉取新会话历史；旧轮次事件按 msgId 找不到消息自然丢弃
  on('conv.activated', (p) => {
    if (!p.id || p.id === chat.convId) return
    chat.convId = p.id
    chat.convTitle = p.title || ''
    chat.messages.splice(0, chat.messages.length)
    chat.generating = false
    currentMsgId = null
    send('chat.history', { sessionId: p.id, limit: 30 })
  })
}

/** 拉取会话列表 */
export function loadConversations() {
  conv.loading = true
  send('conv.list', {})
}

/** 新建对话（服务端创建并激活，conv.activated 广播驱动现场切换） */
export function newConversation() {
  send('conv.create', {})
}

/** 切换到指定对话 */
export function switchConversation(id) {
  if (id === chat.convId) return
  send('conv.activate', { id })
}

/** 重命名对话 */
export function renameConversation(id, title) {
  send('conv.rename', { id, title })
}

/** 删除对话（服务端自动回退激活项并广播） */
export function deleteConversation(id) {
  send('conv.delete', { id })
}

/** 用户发送消息（支持附件） */
export function submitMessage(text, attachments = []) {
  ensureStarted()
  expirePendingInterrupts()
  
  // 提取图片用于前端渲染
  const images = attachments
    .filter(att => att.type === 'image')
    .map(att => `data:${att.mimeType};base64,${att.data}`)
  
  chat.messages.push({
    id: 'u-' + Date.now(),
    role: 'user',
    content: text,
    images: images.length ? images : undefined
  })
  
  send('chat.send', {
    sessionId: chat.convId || socketState.sessionId,
    content: text,
    attachments: attachments.length ? attachments : undefined
  })
  chat.generating = true
}

/** 停止当前轮次生成 */
export function stopGeneration() {
  send('chat.cancel', { sessionId: chat.convId || socketState.sessionId })
}

/** 单个操作的确认/拒绝；全部确认后统一发送 decisions */
export function decideInterrupt(msgId, index, decision) {
  const m = chat.messages.find((x) => x.id === msgId)
  if (!m) return
  if (!m.interruptDecisions) m.interruptDecisions = new Array(m.interruptActions.length).fill(undefined)
  m.interruptDecisions[index] = decision

  const allDecided = m.interruptDecisions.every((d) => d !== undefined)
  if (allDecided) {
    const decisions = m.interruptDecisions.map((d) => ({ type: d }))
    send('tool.confirm', { sessionId: chat.convId || socketState.sessionId, decisions })
    chat.generating = true
    m.interruptActions = null
    m.interruptDecisions = null
  }
}

/** 一键全部允许 */
export function approveAllInterrupt(msgId) {
  const m = chat.messages.find((x) => x.id === msgId)
  if (!m) return
  const decisions = m.interruptActions.map(() => ({ type: 'approve' }))
  m.interruptActions = null
  m.interruptDecisions = null
  send('tool.confirm', { sessionId: chat.convId || socketState.sessionId, decisions })
  chat.generating = true
}

export function useChatStore() {
  ensureStarted()
  loadConversations()
  // 会话对齐：connected 帧已把激活会话写入 socketState.sessionId；
  // 首次进入（convId 未知）按激活会话拉历史，后续切换由 conv.activated 广播驱动
  if (!chat.convId && socketState.sessionId) {
    chat.convId = socketState.sessionId
    send('chat.history', { sessionId: chat.convId, limit: 30 })
  } else if (chat.convId && chat.messages.length === 0 && !chat.generating) {
    // 每次进入聊天页拉取历史：仅在 messages 为空时生效（见 chat.history.result 守卫），
    // 若正在流式中则数据保持不动
    send('chat.history', { sessionId: chat.convId, limit: 30 })
  }
  return { chat, conv, socketState, submitMessage, stopGeneration, decideInterrupt, approveAllInterrupt, loadConversations, newConversation, switchConversation, renameConversation, deleteConversation }
}
