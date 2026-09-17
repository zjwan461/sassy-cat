/**
 * 语音朗读（TTS）模块级单例
 *
 * Phase 1 使用 Web Speech API（window.speechSynthesis），零依赖、无需 GPU。
 * 职责：
 *  - 中文语音枚举（voiceschanged）、语音选择与回退
 *  - 文本预处理：剥离 Markdown、跳过代码块、长文本分段
 *  - 流式自动朗读：播放缓冲（累积 ≥10 字开播、播放会话不中断、尾流超时/完成补读）
 *  - 手动朗读：播放/停止/切换（供聊天气泡按钮）
 *  - 与设置页 voice.* 配置联动，跨 tab 存活
 */
import { reactive, ref } from 'vue'
import { useAgentSocket } from './useAgentSocket'

const api = typeof window !== 'undefined' ? window.electronAPI : null

// ---------- 常量 ----------
const BUFFER_MIN = 10        // 开播门槛：正文（剥离后）累积 ≥10 字才开始播放
const FLUSH_AFTER_MS = 1500  // 尾流兜底：距最后 delta 超过该时长且有未读内容 → 强制补读
const MAX_SENTENCE_CHARS = 200 // 单条 utterance 上限（规避 Chromium 长文本截断）
// 表情符号：图片/旗帜/ZWJ 序列/变体选择符/装饰键帽（朗读时剔除，避免读到 emoji）
const EMOJI_RE = /[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{20E3}\u{FE0F}\u{FE0E}\u{200D}]/gu

// ---------- 状态 ----------
export const ttsState = reactive({
  enabled: false,
  engine: 'web-speech',
  autoRead: false,
  voiceName: '',
  rate: 1.0,
  pitch: 1.0,
  voices: [],     // 全部系统语音
  zhVoices: [],   // 中文语音
  ready: false,   // 是否至少检测到 1 个系统语音
})

// 当前正在朗读的消息 id（跨 tab 存活，供 UI 高亮播放按钮）
export const speaking = ref(null)

// ---------- 文本预处理 ----------

/** 流式安全的 Markdown 剥离：去代码块/行内代码/标题/列表/引用/表格/粗斜体/链接 */
export function stripForSpeech(raw) {
  if (!raw) return ''
  let s = String(raw)
  // 1) 围栏代码块 / 行内代码
  s = s
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/~~~[\s\S]*?~~~/g, ' ')
    .replace(/`[^`\n]*`/g, ' ')
  // 1.5) 表情符号（含旗帜、ZWJ 序列、变体选择符、装饰键帽）
  s = s.replace(EMOJI_RE, ' ')
  // 2) 逐行去块级 Markdown 标记
  const lines = s.split('\n').map((line) => {
    let l = line.replace(/\r/g, '')
    l = l.replace(/^\s{0,3}#{1,6}\s+/, '')            // ATX 标题
    l = l.replace(/^\s{0,3}(?:[-*+]|\d+[.)])\s+/, '') // 列表
    l = l.replace(/^\s{0,3}>+\s?/, '')                // 引用
    l = l.replace(/^\s{0,3}(?:[-_*]){3,}\s*$/, '')    // 分割线
    l = l.replace(/^\s{0,3}\|.*\|\s*$/, '')           // 表格行
    l = l.replace(/\|/g, '')
    l = l.replace(/\*\*(.+?)\*\*/g, '$1')             // 粗体
    l = l.replace(/\*([^*\n]+)\*/g, '$1')             // 斜体
    l = l.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')    // 图片（读 alt）
    l = l.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')     // 链接（读文本）
    return l
  })
  let out = lines.join('\n')
  out = out.replace(/[ \t\u3000]+/g, ' ')             // 压缩空白
  out = out.replace(/\n[ \t]*\n+/g, '\n\n')           // 空行归一
  return out.trim()
}

/** 检查一段文本中是否存在未闭合的内联构造（围栏/加粗/链接），决定能否安全切句 */
function hasUnclosedConstruct(s) {
  const stars = (s.match(/\*\*/g) || []).length
  const ticks = (s.match(/`/g) || []).length
  const bracks = (s.match(/\[/g) || []).length
  return stars % 2 !== 0 || ticks % 2 !== 0 || bracks % 2 !== 0
}

/**
 * 在 prose 的 [start, ...) 中找最后一个「安全句子边界」。
 * 安全 = 该句（start→边界）与紧随其后的片段内均无未闭合内联构造，
 * 保证切出的句子不会因后续 delta 而「回溯改变」；找不到返回 -1。
 */
function findSafeSentEnd(prose, start) {
  const re = /[。！？…!?]+|\n+/g
  re.lastIndex = start
  const ends = []
  let m
  while ((m = re.exec(prose))) ends.push(m.index + m[0].length)
  if (!ends.length) return -1
  for (let i = ends.length - 1; i >= 0; i--) {
    const between = prose.slice(i === 0 ? start : ends[i - 1], ends[i])
    const after = prose.slice(ends[i], i + 1 < ends.length ? ends[i + 1] : prose.length)
    if (!hasUnclosedConstruct(between) && !hasUnclosedConstruct(after)) return ends[i]
  }
  return -1
}

/** 按句切分（供手动朗读/补读分段），超长句再硬切 */
function splitIntoChunks(text) {
  if (!text) return []
  const parts = []
  const re = /[。！？…!?]+|\n+/g
  let last = 0
  let m
  while ((m = re.exec(text))) {
    const end = m.index + m[0].length
    parts.push(text.slice(last, end))
    last = end
  }
  if (last < text.length) parts.push(text.slice(last))
  const out = []
  for (const p of parts) {
    const t = p.trim()
    if (!t) continue
    if (t.length <= MAX_SENTENCE_CHARS) { out.push(t); continue }
    for (let i = 0; i < t.length; i += MAX_SENTENCE_CHARS) out.push(t.slice(i, i + MAX_SENTENCE_CHARS))
  }
  return out
}

// ---------- 语音枚举与选择 ----------

let voiceInit = false
let voicePollTimer = null

function refreshVoices() {
  const synth = window.speechSynthesis
  if (!synth) { ttsState.ready = false; return [] }
  const all = synth.getVoices ? (synth.getVoices() || []) : []
  ttsState.voices = all
  ttsState.zhVoices = all.filter((v) => v.lang && v.lang.toLowerCase().replace('_', '-').startsWith('zh'))
  ttsState.ready = all.length > 0
  return all
}

function startVoiceLoad() {
  if (voiceInit || !window.speechSynthesis) return
  voiceInit = true
  refreshVoices()
  // Chromium 首次 getVoices() 可能为空，需等 voiceschanged
  window.speechSynthesis.addEventListener?.('voiceschanged', refreshVoices)
  // Electron 下 voiceschanged 有时不触发，轮询兜底直到拿到语音列表
  const poll = () => {
    if (ttsState.voices.length) return
    refreshVoices()
    if (!ttsState.voices.length) voicePollTimer = setTimeout(poll, 250)
  }
  setTimeout(poll, 300)
}

/** 选择当前语音：命中配置 voiceName → 任一中文语音 → 默认语音 */
function pickVoice() {
  const all = ttsState.voices.length ? ttsState.voices : refreshVoices()
  if (!all.length) return null
  if (ttsState.voiceName) {
    const hit = all.find((v) => v.name === ttsState.voiceName)
    if (hit) return hit
  }
  const zh = all.find((v) => v.lang && v.lang.toLowerCase().replace('_', '-').startsWith('zh'))
  return zh || all[0]
}

function getZhVoices() {
  if (ttsState.zhVoices.length) return ttsState.zhVoices
  refreshVoices()
  return ttsState.zhVoices
}

// ---------- 播放核心 ----------

let pendingUtterances = 0
let lastCancelAt = 0            // 上次 cancel 时间戳（规避 speak 紧随 cancel 被吞句）
const speakTimers = new Set()   // 延迟 speak 的定时器（stop 时一并清理）

function clearSpeakTimers() {
  for (const t of speakTimers) clearTimeout(t)
  speakTimers.clear()
}

/** 统一取消：仅 cancel()，不做 pause/resume（Windows 下 pause 会让后续 speak 静默） */
function cancelSpeech() {
  const synth = window.speechSynthesis
  if (!synth) return
  try { synth.cancel() } catch { /* ignore */ }
  lastCancelAt = Date.now()
}

function clampRate(v) { const n = Number(v); return Number.isFinite(n) ? Math.min(2, Math.max(0.1, n)) : 1 }
function clampPitch(v) { const n = Number(v); return Number.isFinite(n) ? Math.min(2, Math.max(0, n)) : 1 }

function speakUtterance(text, msgId) {
  const synth = window.speechSynthesis
  if (!synth) return false
  const voice = pickVoice()
  const u = new SpeechSynthesisUtterance(text)
  if (voice) { u.voice = voice; u.lang = voice.lang || 'zh-CN' }
  else u.lang = 'zh-CN'
  u.rate = clampRate(ttsState.rate)
  u.pitch = clampPitch(ttsState.pitch)
  pendingUtterances++
  const dec = () => {
    pendingUtterances = Math.max(0, pendingUtterances - 1)
    if (pendingUtterances === 0) speaking.value = null
  }
  u.onend = dec
  u.onerror = dec
  const fire = () => {
    // 若引擎残留 paused 状态，先恢复再播（否则 speak 会静默排队）
    if (synth.paused) { try { synth.resume() } catch { /* ignore */ } }
    try { synth.speak(u) } catch { dec() }
  }
  // cancel 后立即 speak 的高概率被 Chromium 吞掉：短延迟一拍再出声
  if (Date.now() - lastCancelAt < 80) {
    const t = setTimeout(() => { speakTimers.delete(t); fire() }, 60)
    speakTimers.add(t)
  } else {
    fire()
  }
  return true
}

/** 按句/段入队朗读 */
function enqueueSpeech(text, msgId) {
  const chunks = splitIntoChunks(text || '')
  if (!chunks.length) return
  if (!speaking.value) speaking.value = msgId || speaking.value
  for (const c of chunks) speakUtterance(c, msgId)
}

/** 停止所有朗读（手动停止/切换/新轮次打断） */
export function stop() {
  cancelSpeech()
  clearSpeakTimers()
  pendingUtterances = 0
  speaking.value = null
  resetStream()
}

/**
 * 手动朗读（气泡按钮）：当前播同一消息 → 停止；播其他消息 → 切换；否则 → 播放
 * @returns {boolean} 是否开始播放
 */
export function playMessage(msgId, content) {
  if (!window.speechSynthesis) return false
  if (speaking.value === msgId) { stop(); return false }
  stop()
  enqueueSpeech(stripForSpeech(content), msgId)
  return true
}

/** 设置页试听：可用 opts 临时指定语音/语速/音调（不落盘，播完即还原） */
export function testVoice(text = '喵～本喵就是这么可爱！', opts = {}) {
  if (!window.speechSynthesis) return false
  stop()
  const prev = { voiceName: ttsState.voiceName, rate: ttsState.rate, pitch: ttsState.pitch }
  if (opts.voiceName !== undefined) ttsState.voiceName = opts.voiceName
  if (opts.rate !== undefined) ttsState.rate = clampRate(opts.rate)
  if (opts.pitch !== undefined) ttsState.pitch = clampPitch(opts.pitch)
  enqueueSpeech(text, 'voice-test')
  Object.assign(ttsState, prev)
  return true
}

// ---------- 配置联动 ----------

function clamp(v, lo, hi, fb) { const n = Number(v); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fb }

/** 读取 voice.* 配置并同步到本地状态 */
export async function loadConfig() {
  if (!api) return
  try {
    const res = await api.getConfig()
    if (!res || !res.success) return
    const v = (res.config && res.config.voice) || {}
    ttsState.enabled = v.enabled === true
    ttsState.engine = v.engine || 'web-speech'
    ttsState.autoRead = v.autoRead === true
    ttsState.voiceName = v.voiceName || ''
    ttsState.rate = clamp(v.rate, 0.1, 2, 1)
    ttsState.pitch = clamp(v.pitch, 0, 2, 1)
  } catch { /* ignore */ }
  refreshVoices()
}

/** 保存 voice.* 配置（部分更新） */
export async function saveConfig(partial = {}) {
  if (!api) return { success: false, message: 'electronAPI 不可用' }
  const patches = Object.entries(partial).map(([k, value]) => ({ path: `voice.${k}`, value }))
  const res = await api.setConfigMany(patches)
  if (res && res.success) await loadConfig()
  return res
}

// ---------- 流式自动朗读（播放缓冲） ----------

let fullRaw = ''           // 当前消息累积的原始正文
let spokenProseLen = 0     // 已进入播放队列的剥离文本长度
let streamStarted = false  // 本轮是否已越过开播门槛
let streamMsgId = null
let lastDeltaAt = 0
let flushTimer = null

function resetStream() {
  fullRaw = ''
  spokenProseLen = 0
  streamStarted = false
  lastDeltaAt = 0
  if (flushTimer) { clearTimeout(flushTimer); flushTimer = null }
}

/** 把当前缓冲中「稳定完整的句子」送入播放队列 */
function flusher() {
  const prose = stripForSpeech(fullRaw)
  if (prose.length <= spokenProseLen) return
  // 开播门槛只约束首次启动：正文不足 BUFFER_MIN 时静默等待
  if (!streamStarted && prose.length < BUFFER_MIN) return
  const cut = findSafeSentEnd(prose, spokenProseLen)
  if (cut <= spokenProseLen) return
  const toSpeak = prose.slice(spokenProseLen, cut)
  spokenProseLen = cut
  streamStarted = true
  enqueueSpeech(toSpeak, streamMsgId)
}

/** 补读残余（尾流超时 / 流结束强制） */
function flushTail(force = false) {
  if (!ttsState.enabled || !ttsState.autoRead) return
  if (!streamMsgId) return
  const prose = stripForSpeech(fullRaw)
  if (spokenProseLen >= prose.length) return
  if (force || streamStarted) {
    enqueueSpeech(prose.slice(spokenProseLen), streamMsgId)
    spokenProseLen = prose.length
  }
}

function armFlushTimer() {
  if (flushTimer) clearTimeout(flushTimer)
  flushTimer = setTimeout(() => {
    flushTimer = null
    if (!ttsState.enabled || !ttsState.autoRead) return
    if (!streamMsgId || !fullRaw) return
    if (Date.now() - lastDeltaAt < FLUSH_AFTER_MS) return
    flushTail(true)
  }, FLUSH_AFTER_MS + 50)
}

function onChatStarted(p) {
  if (p.msgId === streamMsgId) return // 同消息续跑（工具/中断后），保持现场
  // 新轮次：停止上一轮语音并复位缓冲
  speechCancelSilent()
  resetStream()
  streamMsgId = p.msgId
}

function onChatDelta(p) {
  if (!ttsState.enabled || !ttsState.autoRead) return
  if (p.msgId !== streamMsgId) return
  if (!p.text) return
  fullRaw += p.text
  lastDeltaAt = Date.now()
  flusher()
  armFlushTimer()
}

function onChatCompleted(p) {
  if (p.msgId !== streamMsgId) return
  // 以服务端最终全文为准（可能比增量拼接更完整）
  if (p.text && p.text.length > fullRaw.length) fullRaw = p.text
  flushTail(true)
  streamMsgId = null
}

function onChatError(p) {
  if (p.msgId !== streamMsgId) return
  flushTail(true)
  streamMsgId = null
}

function speechCancelSilent() {
  cancelSpeech()
  clearSpeakTimers()
  pendingUtterances = 0
  speaking.value = null
}

// ---------- 模块初始化（单例守卫） ----------

let started = false

function ensureStarted() {
  if (started) return
  started = true
  const { on } = useAgentSocket()
  on('chat.started', onChatStarted)
  on('chat.delta', onChatDelta)
  on('chat.completed', onChatCompleted)
  on('chat.error', onChatError)
  on('conv.activated', () => { speechCancelSilent(); resetStream() })
  startVoiceLoad()
  loadConfig()
}

export function useTTS() {
  ensureStarted()
  return {
    ttsState,
    speaking,
    loadConfig,
    saveConfig,
    getZhVoices,
    stripForSpeech,
    playMessage,
    stop,
    testVoice,
  }
}