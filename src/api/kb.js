/**
 * 知识库 HTTP API 模块
 * 知识库 CRUD、文档上传/删除、文档分块 SSE 流式加载。
 */
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

/** 列出全部知识库 */
export function listKbs() {
  return request('/api/kb')
}

/** 创建知识库 */
export function createKb(name, description = '') {
  return request('/api/kb', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
}

/** 更新知识库 */
export function updateKb(kbId, name, description = '') {
  return request(`/api/kb/${kbId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
}

/** 删除知识库（含向量清理） */
export function deleteKb(kbId) {
  return request(`/api/kb/${kbId}`, { method: 'DELETE' })
}

/** 列出知识库下全部文档 */
export function listDocuments(kbId) {
  return request(`/api/kb/${kbId}/documents`)
}

/** 上传文件入库（OCR -> 分块 -> embedding，可能较慢） */
export function uploadDocument(kbId, file) {
  const formData = new FormData()
  formData.append('file', file)
  return request(`/api/kb/${kbId}/documents`, {
    method: 'POST',
    body: formData,
  })
}

/** 删除文档（含向量清理） */
export function deleteDocument(kbId, docId) {
  return request(`/api/kb/${kbId}/documents/${docId}`, { method: 'DELETE' })
}

/**
 * 分页查询知识库文档分块（信息流滚动加载）。
 * @param {string} kbId 知识库 ID
 * @param {number} page 页码（从 1 开始）
 * @param {number} pageSize 每页数量
 * @param {string} [docId] 按文档过滤（可选）
 * @returns {Promise<{items: Array, total: number, page: number, pageSize: number}>}
 */
export function fetchChunks(kbId, page = 1, pageSize = 20, docId = '') {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (docId) params.set('doc_id', docId)
  return request(`/api/kb/${kbId}/chunks?${params}`)
}
