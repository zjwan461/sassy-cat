/**
 * 消息历史 HTTP API 模块
 * 通过 REST 接口查询聊天历史，支持分页。
 */
import { useAgentSocket } from '../composables/useAgentSocket'

const { state: socketState } = useAgentSocket()

/**
 * 分页查询历史消息（含附件）
 * @param {string} sessionId 会话 ID
 * @param {number} page 页码（从 1 开始）
 * @param {number} pageSize 每页数量
 * @returns {Promise<{items: Array, total: number, page: number, pageSize: number}>}
 */
export async function fetchMessages(sessionId, page = 1, pageSize = 20) {
  const port = socketState.port
  const params = new URLSearchParams({
    session_id: sessionId,
    page: String(page),
    page_size: String(pageSize),
  })

  const response = await fetch(
    `http://127.0.0.1:${port}/api/messages?${params}`
  )

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  return response.json()
}
