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
  generating: false
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
}

/** 用户发送消息 */
export function submitMessage(text) {
  ensureStarted()
  expirePendingInterrupts()
  chat.messages.push({ id: 'u-' + Date.now(), role: 'user', content: text })
  send('chat.send', { sessionId: socketState.sessionId, content: text })
  chat.generating = true
}

/** 停止当前轮次生成 */
export function stopGeneration() {
  send('chat.cancel', { sessionId: socketState.sessionId })
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
    send('tool.confirm', { sessionId: socketState.sessionId, decisions })
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
  send('tool.confirm', { sessionId: socketState.sessionId, decisions })
  chat.generating = true
}

export function useChatStore() {
  ensureStarted()
  // 每次进入聊天页拉取历史：仅在 messages 为空时生效（见 chat.history.result 守卫），
  // 若正在流式中则数据保持不动
  send('chat.history', { sessionId: socketState.sessionId, limit: 50 })
  return { chat, socketState, submitMessage, stopGeneration, decideInterrupt, approveAllInterrupt }
}
