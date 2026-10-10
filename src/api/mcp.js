/**
 * MCP 服务注册与发现 HTTP API 模块
 * 注册表存储于用户数据目录（%APPDATA%/sassy-cat/mcp-servers.json）。
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

const JSON_HEADERS = { 'Content-Type': 'application/json' }

/** 列出全部已注册的 MCP server */
export function listServers() {
  return request('/api/mcp')
}

/** 注册 MCP server */
export function createServer(payload) {
  return request('/api/mcp', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  })
}

/** 更新 MCP server 配置 */
export function updateServer(name, payload) {
  return request(`/api/mcp/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  })
}

/** 删除 MCP server 注册 */
export function deleteServer(name) {
  return request(`/api/mcp/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

/** 批量导入（粘贴 mcpServers 风格 JSON） */
export function importServers(content, overwrite = false) {
  return request('/api/mcp/import', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ content, overwrite }),
  })
}

/** 连接测试 + 工具发现（耗时可能达 20s，前端不设超时） */
export function testServer(name) {
  return request(`/api/mcp/${encodeURIComponent(name)}/test`, {
    method: 'POST',
  })
}

/** 导出注册表（mcpServers 风格 JSON 对象） */
export function exportServers(names = []) {
  const q = names.length ? `?names=${encodeURIComponent(names.join(','))}` : ''
  return request(`/api/mcp/export${q}`)
}
