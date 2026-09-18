/**
 * Dashboard 报表统计 API 模块
 * 直连本地 Python 服务，获取对话/Token/知识库聚合数据与逐日趋势。
 */
import { useAgentSocket } from '../composables/useAgentSocket'

function baseUrl() {
  return `http://127.0.0.1:${useAgentSocket().state.port}`
}

/**
 * 获取 Dashboard 报表聚合数据
 * @param {number} trendDays 趋势图天数（含今日），默认 7
 * @returns {Promise<{
 *   chat: { today: number, total: number },
 *   token: { today: { inputTokens, outputTokens, totalTokens }, total: { inputTokens, outputTokens, totalTokens } },
 *   kb: { kbCount, docCount, chunkCount, perKb: Array<{ name, docCount, chunkCount }> },
 *   trend: Array<{ date: string, chats: number, tokens: number }>,
 * }>}
 */
export async function fetchDashboardStats(trendDays = 7) {
  const url = `${baseUrl()}/api/stats/dashboard?trend_days=${trendDays}`
  let response
  try {
    response = await fetch(url)
  } catch (e) {
    // 网络层失败（服务未启动 / 端口未就绪 / 连接被拒）：浏览器只给 "Failed to fetch"，这里补上目标地址
    throw new Error(`连不上本地服务 ${url}（${e.message}）`)
  }
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }
  return response.json()
}
