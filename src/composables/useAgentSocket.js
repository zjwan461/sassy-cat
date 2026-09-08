/**
 * Agent WebSocket 客户端（单例 + 自动重连 + 离线队列）
 * 设计稿 4.4 节。所有渲染窗口（主窗口聊天页 / 桌宠）共用同一模块实例。
 */
import { reactive } from 'vue'

const DEFAULT_PORT = 8790

const state = reactive({
  status: 'closed', // connecting | open | reconnecting | closed
  port: DEFAULT_PORT,
  client: 'main', // main | pet（由 setClient 在各窗口入口设置）
  // 会话 id 由服务端 connected 帧下发（激活会话），本地值仅作为连接 query 的占位/上次值；
  // 多会话切换（conv.activated）时会随之更新
  sessionId: localStorage.getItem('sassy.sessionId') || ''
})

export function setClient(c) { state.client = c }

let ws = null
let retryDelay = 1000
const MAX_RETRY_DELAY = 30000
let reconnectTimer = null
let offlineQueue = []
const listeners = new Map() // type -> Set<fn>

function emit(type, payload) {
  const set = listeners.get(type)
  if (set) for (const fn of set) {
    try { fn(payload) } catch (e) { console.error('[ws] listener error', e) }
  }
}

export function on(type, fn) {
  if (!listeners.has(type)) listeners.set(type, new Set())
  listeners.get(type).add(fn)
  return () => listeners.get(type).delete(fn)
}
function url() {
  const sid = state.sessionId ? `&sessionId=${state.sessionId}` : ''
  return `ws://127.0.0.1:${state.port}/ws/agent?client=${state.client}${sid}`
}

function flushQueue() {
  const pending = offlineQueue.slice()
  offlineQueue = []
  pending.forEach((frame) => ws && ws.send(JSON.stringify(frame)))
}

export function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  state.status = state.status === 'reconnecting' ? 'reconnecting' : 'connecting'
  try {
    ws = new WebSocket(url())
  } catch (e) {
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    state.status = 'open'
    retryDelay = 1000
    flushQueue()
    emit('__open__', {})
  }
  ws.onmessage = (evt) => {
    let frame
    try { frame = JSON.parse(evt.data) } catch { return }
    // 服务端为准对齐激活会话：connected 帧携带当前 activeId；
    // 变化时先更新 sessionId 再派发，保证业务监听器看到的是新会话
    if (frame.type === 'connected' && frame.payload?.sessionId && frame.payload.sessionId !== state.sessionId) {
      state.sessionId = frame.payload.sessionId
      localStorage.setItem('sassy.sessionId', state.sessionId)
    }
    // 会话切换广播（conv.activate/create/delete 由服务端权威处理）：
    // 在派发业务监听器之前更新 sessionId，使 send() 落入新房间、
    // 桌宠等直接读 state.sessionId 的消费方自动跟随
    if (frame.type === 'conv.activated' && frame.payload?.id && frame.payload.id !== state.sessionId) {
      state.sessionId = frame.payload.id
      localStorage.setItem('sassy.sessionId', state.sessionId)
    }
    emit(frame.type, frame.payload || {})
  }
  ws.onclose = () => {
    ws = null
    emit('__close__', {})
    scheduleReconnect()
  }
  ws.onerror = () => { /* onclose 会跟着触发 */ }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  state.status = 'reconnecting'
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY)
    connect()
  }, retryDelay)
}

export function send(type, payload = {}) {
  const frame = { v: 1, id: 'c-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6), ts: Date.now(), type, payload }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(frame))
  } else {
    offlineQueue.push(frame)
    connect()
  }
}

/** 设置由 Electron agent-ready 上报的端口 */
export function setPort(port) {
  if (port && port !== state.port) {
    state.port = port
    if (ws) { ws.onclose = null; ws.close(); ws = null }
    connect()
  }
}

export function useAgentSocket() {
  return { state, connect, send, on, setPort }
}
