/**
 * 下载 RAG 本地 embedding 模型
 * 调用 Python 后端的 smart_download：自动探测 huggingface.co 可达性选择镜像，
 * 按本机显卡显存智能选择大/小模型。
 */
import { useAgentSocket } from '../composables/useAgentSocket'

const { state: socketState } = useAgentSocket()

function baseUrl() {
  return `http://127.0.0.1:${socketState.port}`
}

/**
 * 触发下载本地 embedding 模型。
 * 下载耗时可能达分钟级，调用方需自行处理 loading 状态。
 * @returns {Promise<{status: string, path: string}>} path 为模型本地目录
 */
export async function downloadEmbeddingModel() {
  const response = await fetch(`${baseUrl()}/api/rag/model/download`, {
    method: 'POST',
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }
  return response.json()
}
