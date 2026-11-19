/**
 * 本地语音合成（GPT-SoVITS）HTTP API
 *
 * 后端接口见 python/server/tts_api.py：
 *   GET  /api/tts/status   引擎状态
 *   GET  /api/tts/voices   音色列表
 *   POST /api/tts/say      合成（返回 wav）
 *   POST /api/tts/voice    切换音色
 *   POST /api/tts/preload  触发加载
 *
 * 约定：任何接口失败都返回 503，调用方应静默回落到系统语音，不要让对话卡住。
 */
import { useAgentSocket } from '../composables/useAgentSocket'

const { state: socketState } = useAgentSocket()

function baseUrl() {
  return `http://127.0.0.1:${socketState.port}`
}

async function readError(response) {
  try {
    const body = await response.json()
    return body.detail || `HTTP ${response.status}`
  } catch {
    return `HTTP ${response.status}`
  }
}

/** 引擎状态：{ engine, enabled, available, loading, error, voice, voices[], device } */
export async function getStatus() {
  const res = await fetch(`${baseUrl()}/api/tts/status`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

/** 音色列表：[{ name, version, language, hasReferenceAudio, usable }] */
export async function listVoices() {
  const res = await fetch(`${baseUrl()}/api/tts/voices`)
  if (!res.ok) throw new Error(await readError(res))
  const body = await res.json()
  return body.voices || []
}

/** 热切换音色（毫秒级） */
export async function switchVoice(name) {
  const res = await fetch(`${baseUrl()}/api/tts/voice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

/** 触发加载/预热（设置页开启本地语音时调用，给用户一个明确的“正在准备”状态） */
export async function preload() {
  const res = await fetch(`${baseUrl()}/api/tts/preload`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

/**
 * 合成一段文本，返回 object URL（调用方负责 URL.revokeObjectURL）。
 * 失败会抛出异常，由调用方决定是跳过这一句还是回落系统语音。
 */
export async function say(text, { voice, speed, signal } = {}) {
  const res = await fetch(`${baseUrl()}/api/tts/say`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice: voice || null, speed: speed || null }),
    signal,
  })
  if (!res.ok) throw new Error(await readError(res))
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

// ---------------------------------------------------------------------------
// 模型按需下载（权重不进仓库，也不进安装包）
// ---------------------------------------------------------------------------

/** 启动下载。packages 为空表示下载全部（基础模型 + 所有音色）。 */
export async function startDownload(packages) {
  const res = await fetch(`${baseUrl()}/api/tts/download/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(packages ? { packages } : {}),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

/**
 * 下载进度：{ state, percent, doneBytes, totalBytes, currentFile, error, missingModels[] }
 * state ∈ idle | running | done | failed | cancelled
 */
export async function downloadStatus() {
  const res = await fetch(`${baseUrl()}/api/tts/download/status`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

export async function cancelDownload() {
  const res = await fetch(`${baseUrl()}/api/tts/download/cancel`, { method: 'POST' })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}