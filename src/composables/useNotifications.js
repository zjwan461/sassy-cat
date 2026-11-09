/**
 * 全局通知中心（模块级单例）。
 *
 * 汇聚三类消息，避免它们只出现在托盘/桌宠气泡/日志里而被错过：
 * - 提醒事项（proactive.reminder / proactive.message）
 * - 后台任务结果（知识库索引重建、文档入库失败）
 * - 系统提示（可在任意页面 add）
 *
 * 仅保留内存态：应用重启后清空，避免把临时事件当历史数据持久化。
 */
import { computed, reactive } from 'vue'

const state = reactive({
  items: [],
  panelOpen: false,
})

let seq = 0
const MAX_ITEMS = 80

export const notifications = state.items
export const items = state.items
export const unreadCount = computed(() => state.items.filter((n) => !n.read).length)
export const unreadBadge = computed(() => (unreadCount.value > 9 ? '9+' : String(unreadCount.value)))
export const panelOpen = computed(() => state.panelOpen)

/**
 * 新增一条通知。
 * @param {object} payload
 * @param {string} payload.title 标题
 * @param {string} [payload.body] 正文
 * @param {'reminder'|'success'|'error'|'info'} [payload.kind]
 * @param {string} [payload.action] 点击后跳转的路由（如 /chat、/kb/kb-id）
 * @param {string} [payload.actionLabel] 跳转按钮文案
 */
export function addNotification({ title, body = '', kind = 'info', action = '', actionLabel = '' }) {
  if (!title) return
  seq += 1
  state.items.unshift({
    id: `n-${Date.now()}-${seq}`,
    title: String(title),
    body: String(body || ''),
    kind,
    action,
    actionLabel,
    ts: Date.now(),
    read: false,
  })
  if (state.items.length > MAX_ITEMS) state.items.length = MAX_ITEMS
}

export function markRead(id) {
  const item = state.items.find((n) => n.id === id)
  if (item) item.read = true
}

export function markAllRead() {
  for (const item of state.items) item.read = true
}

export function removeNotification(id) {
  const idx = state.items.findIndex((n) => n.id === id)
  if (idx !== -1) state.items.splice(idx, 1)
}

export function clearNotifications() {
  state.items.splice(0, state.items.length)
}

export function togglePanel(value) {
  state.panelOpen = typeof value === 'boolean' ? value : !state.panelOpen
  if (state.panelOpen) markAllRead()
}

export function useNotifications() {
  return {
    items: state.items,
    unreadCount,
    unreadBadge,
    panelOpen,
    addNotification,
    markRead,
    markAllRead,
    removeNotification,
    clearNotifications,
    togglePanel,
  }
}
