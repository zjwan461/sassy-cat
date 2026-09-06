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
  sessionId: localStorage.getItem('sassy.sessionId') || ('web-' + Math.random().toString(36).slice(2, 10))
})
localStorage.setItem('sassy.sessionId', state.sessionId)

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
  return `ws://127.0.0.1:${state.port}/ws/agent?client=${state.client}&sessionId=${state.sessionId}`
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
