/**
 * 聊天会话状态（模块级单例）
 *
 * 消息列表、轮次状态以及所有 WebSocket 事件订阅都挂在模块作用域，
 * 与 ChatView 组件的挂载/卸载解耦：切换 tab 时组件销毁也不会停止
 * 流式渲染数据的接收与累积，切回来直接恢复现场继续渲染。
 */
import { reactive } from 'vue'
import { useAgentSocket } from './useAgentSocket'
import { fetchMessages } from '../api/messages'

const { state: socketState, connect, send, on } = useAgentSocket()

export const chat = reactive({
  messages: [],
  generating: false,
  // 当前会话（对话）：id 即 LangGraph thread_id，由服务端激活会话下发
  convId: null,
  convTitle: '',
  // 分页相关（历史消息通过 HTTP 接口分页加载）
  currentPage: 1,
  pageSize: 20,
  totalMessages: 0,
  loadingMore: false,
  hasMore: true,
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
    // 检测是否在工具调用/中断后继续输出：若最后一条助手消息有工具或曾中断，则复用该消息而非创建新消息
    // resuming：确认中断后本地已清空 interruptActions，需靠标记识别"确认后即将续跑"
    const last = chat.messages[chat.messages.length - 1]
    const hasTools = last?.tools && last.tools.length > 0
    const wasInterrupted = last?.interruptActions || last?.interruptExpired || last?.resuming
    if (last) last.resuming = false
    if (last && last.role === 'assistant' && (hasTools || wasInterrupted)) {
      // 复用现有消息：更新 id 以匹配新的 msgId，保持 tools 和内容
      last.id = p.msgId
      last.streaming = true
      last.thinking = false
      // 清除中断状态，因为现在继续输出了
      last.interruptActions = null
      last.interruptDecisions = null
      last.interrupt = null
      // 中断确认后续跑属于新一轮思考，即使消息已有正文也要重新展开深度思考区；
      // 工具调用后正常续跑则不重置 reasoningOpen，保留用户之前的折叠状态
      if ((!last.content && !last.reasoning) || wasInterrupted) {
        last.thinking = true
        last.reasoningOpen = true
      }
    } else {
      chat.messages.push({ id: p.msgId, role: 'assistant', content: '', reasoning: '', reasoningOpen: true, streaming: true, thinking: false, tools: [] })
    }
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
      // 思考阶段进行中（chat.started 已点亮 thinking，如中断续跑场景）时保持展开；
      // 否则沿用正文守卫：一旦消息已开始输出正文，reasoning 只静默追加，
      // 不再点亮"思考中"或展开思考区
      if (!m.content || m.thinking) {
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
      // 保存 toolCallId：供 tool_result 精准回填结果到对应步骤
      // （无 id 时回退为"最近未完成步骤"匹配，见 agent.tool_result）
      m.tools.push({ toolCallId: p.toolCallId, name: p.name, done: false, args: '' })
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
  on('agent.tool_result', (p) => {
    // 工具执行结果：优先按 toolCallId 精准匹配；无 id 时回退到
    // 最近一个未完成（或名称匹配）的步骤，标记完成并回填执行结果
    const m = chat.messages.find((x) => x.id === p.msgId)
    if (!m || !m.tools || !m.tools.length) return
    let t = null
    if (p.toolCallId) t = m.tools.find((x) => x.toolCallId === p.toolCallId)
    if (!t && p.toolCallId) t = [...m.tools].reverse().find((x) => x.name === p.toolName && !x.done)
    if (!t) t = [...m.tools].reverse().find((x) => !x.done)
    if (t) {
      t.done = true
      t.status = 'success'
      t.result = prettyArgs(p.text || '')
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
    loadMessages(true)
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
    loadMessages(true)
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
    images: images.length ? images : undefined,
  })

  const len = chat.messages.length
  send('chat.send', {
    sessionId: chat.convId || socketState.sessionId,
    content: text,
    attachments: attachments.length ? attachments : undefined,
    lastAssistantMsgId: len >=2 ?chat.messages[len-2].id: null
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
    const decisions = m.interruptDecisions.map((d) => {
      if (!d.type) {
        return { type: d }
      }
      return d
    })
    send('tool.confirm', { sessionId: chat.convId || socketState.sessionId, decisions, msgId: msgId })
    chat.generating = true
    // 标记续跑：chat.started 到达前本地 interruptActions 已清空，
    // 靠此标记让续跑分支识别中断场景并重新展开深度思考区
    m.resuming = true
    m.interruptActions = null
    m.interruptDecisions = null
  }
}

/** 一键全部允许 */
export function approveAllInterrupt(msgId) {
  const m = chat.messages.find((x) => x.id === msgId)
  if (!m) return
  const decisions = m.interruptActions.map(() => ({ type: 'approve' }))
  m.resuming = true
  m.interruptActions = null
  m.interruptDecisions = null
  send('tool.confirm', { sessionId: chat.convId || socketState.sessionId, decisions, msgId: msgId })
  chat.generating = true
}

// ---------- 历史消息加载（HTTP 接口） ----------

/**
 * 转换后端消息格式为前端格式
 * 后端返回的消息按 created_at DESC 排序（最新的在前），
 * 前端需要按时间正序显示（旧的在上、新的在下），所以加载后要反转。
 */
function transformMessage(item) {
  // 构建工具调用列表（合并 toolCalls、toolCallArgs、toolCallResult）
  // toolCalls 现在是对象数组（[{tool_call_id, tool_name}]），与 toolCallArgs 一一对应
  const tools = []
  if (item.toolCalls && Array.isArray(item.toolCalls)) {
    const args = item.toolCallArgs || []
    // toolCallResult 数据库里是 JSON 字符串（[{tool_call_id, tool_name, text}]），
    // 接口可能原样返回字符串也可能已解析为数组，两种都兼容
    let results = []
    if (Array.isArray(item.toolCallResult)) {
      results = item.toolCallResult
    } else if (item.toolCallResult) {
      try { results = JSON.parse(item.toolCallResult) || [] } catch { results = [] }
    }
    for (let i = 0; i < item.toolCalls.length; i++) {
      const name = item.toolCalls[i].tool_name
      const toolCallId = item.toolCalls[i].tool_call_id
      const rawArgs = args[i]
      // 按 tool_call_id 匹配对应的执行结果；无 id 时回退按下标取
      const matched = toolCallId
        ? results.find((r) => r.tool_call_id === toolCallId)
        : results[i]
      tools.push({
        toolCallId,
        name,
        done: true,
        args: rawArgs ? prettyArgs(typeof rawArgs === 'string' ? rawArgs : JSON.stringify(rawArgs)) : '',
        result: matched?.text ? prettyArgs(matched.text) : '',
      })
    }
  }

  // 转换附件
  const attachments = (item.attachments || []).map((att) => ({
    id: att.id,
    type: att.type,
    fileName: att.fileName,
    fileExt: att.fileExt,
    fileSize: att.fileSize,
    mimeType: att.mimeType,
    base64Data: att.base64Data,
    markdownContent: att.markdownContent,
  }))

  // 提取图片（用于兼容现有的 images 渲染逻辑）
  const images = attachments
    .filter((a) => a.type === 'image' && a.base64Data)
    .map((a) => `data:${a.mimeType || 'image/png'};base64,${a.base64Data}`)

  // 转换interruptActions
  const interruptActions = (JSON.parse(item.interruptActions) || []).map((item) => ({
    name: item.name,
    argsText: item.args,
  }))

  // 转换interruptDecisions
  const interruptDecisions = (JSON.parse(item.interruptDecisions) || [])

  console.log(item)

  return {
    id: item.id,
    role: item.role,
    content: item.content || '',
    reasoning: item.reasoning || '',
    reasoningOpen: false,
    thinking: false,
    tools,
    attachments,
    images: images.length ? images : undefined,
    interruptActions: interruptActions,
    interruptDecisions: interruptDecisions,
  }
}

/**
 * 加载历史消息（HTTP 分页接口）
 * @param {boolean} reset 是否重置（从第一页开始，清空现有消息）
 */
export async function loadMessages(reset = false) {
  if (!chat.convId) return
  if (chat.loadingMore) return

  if (reset) {
    chat.currentPage = 1
    chat.hasMore = true
  }

  chat.loadingMore = true
  try {
    const result = await fetchMessages(chat.convId, chat.currentPage, chat.pageSize)
    const items = (result.items || []).map(transformMessage)

    if (reset) {
      // 重置：后端返回按时间倒序，反转为正序后写入
      chat.messages.splice(0, chat.messages.length, ...items.reverse())
    } else {
      // 加载更多（之前的页）：后端返回按时间倒序，反转后插入到头部
      chat.messages.splice(0, 0, ...items.reverse())
    }

    chat.totalMessages = result.total || 0
    chat.currentPage++
    // 判断是否还有更多
    const loadedCount = chat.messages.filter((m) => m.role === 'user' || m.role === 'assistant').length
    chat.hasMore = loadedCount < chat.totalMessages
  } catch (e) {
    console.warn('[chat] 加载历史消息失败:', e)
  } finally {
    chat.loadingMore = false
  }
}

/**
 * 加载更多历史消息（向上翻页）
 */
export async function loadMoreMessages() {
  if (!chat.hasMore || chat.loadingMore) return
  await loadMessages(false)
}

export function useChatStore() {
  ensureStarted()
  loadConversations()
  // 会话对齐：connected 帧已把激活会话写入 socketState.sessionId；
  // 首次进入（convId 未知）按激活会话拉历史，后续切换由 conv.activated 广播驱动
  if (!chat.convId && socketState.sessionId) {
    chat.convId = socketState.sessionId
    loadMessages(true)
  } else if (chat.convId && chat.messages.length === 0 && !chat.generating) {
    // 每次进入聊天页拉取历史：仅在 messages 为空时生效，
    // 若正在流式中则数据保持不动
    loadMessages(true)
  }
  return {
    chat, conv, socketState,
    submitMessage, stopGeneration, decideInterrupt, approveAllInterrupt,
    loadConversations, newConversation, switchConversation, renameConversation, deleteConversation,
    loadMessages, loadMoreMessages,
  }
}
