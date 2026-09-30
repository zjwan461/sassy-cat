/**
 * 技能（Skills）HTTP API 模块
 * 列出 runtime/skills 下技能、技能详情（目录树）、文件读取与保存。
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

/** 列出全部技能（卡片数据） */
export function listSkills() {
  return request('/api/skills')
}

/** 新建技能目录（后端自动生成 SKILL.md 骨架） */
export function createSkill(name) {
  return request('/api/skills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

/** 删除整个技能目录（不可恢复） */
export function deleteSkill(name) {
  return request(`/api/skills/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

/** 技能详情：{ skill, tree, skillMd } */
export function getSkill(name) {
  return request(`/api/skills/${encodeURIComponent(name)}`)
}

/** 导出技能：下载 zip 包 */
export async function exportSkill(name) {
  const response = await fetch(`${baseUrl()}/api/skills/${encodeURIComponent(name)}/export`)
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
    throw new Error(err.detail || `HTTP ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}.zip`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 导入技能：上传 zip 包，可选指定名称与覆盖 */
export function importSkill(file, { name = '', overwrite = false } = {}) {
  const form = new FormData()
  form.append('file', file)
  if (name) form.append('name', name)
  if (overwrite) form.append('overwrite', 'true')
  return request('/api/skills/import', {
    method: 'POST',
    body: form,
  })
}

/** 读取技能内某个文本文件：{ path, content } */
export function readSkillFile(name, path) {
  return request(`/api/skills/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`)
}

/** 保存技能内某个文本文件 */
export function writeSkillFile(name, path, content) {
  return request(`/api/skills/${encodeURIComponent(name)}/file`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  })
}

/** 在技能内新增文本文件（可带相对子目录） */
export function createSkillFile(name, path, content = '') {
  return request(`/api/skills/${encodeURIComponent(name)}/file`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, content }),
  })
}

/** 删除技能内某个文件（连同 .bak 备份一并清理） */
export function deleteSkillFile(name, path) {
  return request(`/api/skills/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`, {
    method: 'DELETE',
  })
}
