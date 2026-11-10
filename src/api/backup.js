/** 数据备份 HTTP API */
import { useAgentSocket } from '../composables/useAgentSocket'

const { state: socketState } = useAgentSocket()

function baseUrl() {
  return `http://127.0.0.1:${socketState.port}`
}

async function request(path, options = {}) {
  const response = await fetch(`${baseUrl()}${path}`, options)
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 导出数据备份到指定目录。
 * 返回 { path, items, totalSize, excluded }
 */
export function exportBackup(targetDir) {
  return request('/api/backup/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ targetDir }),
  })
}
