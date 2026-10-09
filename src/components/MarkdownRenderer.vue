<template>
  <!-- 双容器增量渲染：
       .md-stable 只追加、永不重写 —— 已定稿的块只渲染一次，其 DOM 节点身份不变，
                  横向滚动位置、文本选区、图片加载状态都不再被重置
       .md-live   只渲染"仍可能变化的尾部"（通常是最后一个块），随分界点前移而"搬家"到 stable
       注意：两个容器在模板里必须没有子节点，其内容完全由脚本接管
             （Vue 不会清理"无 vnode 子节点"的元素，这是官方允许的手动 DOM 用法） -->
  <div class="markdown-body" ref="rootRef" :class="{ 'md-full': done }" @click="onClick">
    <div class="md-stable" ref="stableRef"></div>
    <div class="md-live" ref="liveRef"></div>
  </div>
  <!-- HTML 代码块预览弹窗：iframe 沙箱渲染（allow-scripts 但不含 allow-same-origin，隔离宿主环境） -->
  <Teleport to="body">
    <div v-if="previewVisible" class="md-preview-modal" @click.self="closePreview" @keydown.esc="closePreview">
      <div class="md-preview-panel" tabindex="-1" ref="previewPanelRef">
        <div class="md-preview-head">
          <span class="md-preview-title">🌐 HTML 预览</span>
          <button class="md-preview-close" type="button" title="关闭" @click="closePreview">✕</button>
        </div>
        <iframe class="md-preview-frame" :srcdoc="previewContent" sandbox="allow-scripts" frameborder="0"></iframe>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import hljs from 'highlight.js/lib/common'
import { createStreamSplitter } from '../utils/streamSplitter'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/atom-one-dark.css'

const props = defineProps({
  // markdown 原文
  content: { type: String, default: '' },
  // 消息是否已完成（流式期间为 false：Mermaid 图延迟到完成后渲染）
  done: { type: Boolean, default: true },
})

// 本帧渲染完成（DOM 已更新、浏览器尚未绘制）时通知父组件，供其做贴底跟随：
// 贴底动作与内容增长落在同一帧内，可消除"先滚到底、内容随后长高"的抖动
const emit = defineEmits(['rendered'])

const rootRef = ref(null)
const stableRef = ref(null) // 已定稿区域：脚本接管、只追加、永不重写
const liveRef = ref(null) // 活动尾部：脚本接管，可整段覆盖或原地追加文本

// HTML 转义（用于把代码文本安全地放进 innerHTML）。
// 直接复用 markdown-it 自带的转义实现，避免手写实体替换出错：
// 原实现把实体替换写成了恒等变换（`&` 仍是 `&`），未高亮的代码块里
// 出现 `<script>` 之类会被当成真实 HTML 注入，必须真正转义
function escapeHtml(s) {
  return md.utils.escapeHtml(String(s))
}

// 语言别名：highlight.js/lib/common 注册的是正式名，模型常写缩写
const LANG_ALIAS = {
  py: 'python', js: 'javascript', ts: 'typescript',
  sh: 'bash', shell: 'bash', zsh: 'bash', ps1: 'powershell',
  yml: 'yaml', md: 'markdown', htm: 'html',
  'c++': 'cpp', 'c#': 'csharp',
}
function normalizeLang(lang) {
  const l = (lang || '').trim().toLowerCase()
  return LANG_ALIAS[l] || l
}

// 超过该长度不做语法高亮：极端长代码块的高亮成本远大于收益
const MAX_HIGHLIGHT_CHARS = 20000

// 只高亮"已知语言"的代码，未知语言一律按纯文本转义。
// 原先未知语言走 hljs.highlightAuto()，它会依次尝试全部内置语法并打分选优
// （O(n × 语法数)）；在流式逐帧重渲染的场景下这是最大的性能黑洞，必须去掉。
function highlightCode(code, lang) {
  const l = normalizeLang(lang)
  if (!l || l === 'text' || l === 'plaintext' || code.length > MAX_HIGHLIGHT_CHARS) {
    return escapeHtml(code)
  }
  if (!hljs.getLanguage(l)) return escapeHtml(code)
  try {
    return hljs.highlight(code, { language: l }).value
  } catch {
    return escapeHtml(code)
  }
}

const md = new MarkdownIt({
  html: false, // 禁止原始 HTML，防 XSS
  linkify: true,
  breaks: true, // 单个换行也换行，符合聊天习惯
  highlight: highlightCode,
})

md.use(texmath, {
  engine: katex,
  delimiters: ['dollars', 'brackets'], // $...$ / $$...$$ 与 \( \) / \[ \]
  katexOptions: { throwOnError: false, output: 'html' },
  classesForModern: false,
})

// 代码块外壳：fence 规则与"未闭合代码块"快速路径共用同一套结构，
// 保证流式/定稿两种形态的样式与交互（复制/预览按钮）完全一致
function codeBlockHtml(label, bodyHtml, { preview = false, streaming = false, hljsClass = '' } = {}) {
  const previewBtn = preview
    ? `<button class="md-preview" type="button" title="在弹窗中预览 HTML">🌐 预览</button>`
    : ''
  const copyBtn = `<button class="md-copy" type="button" title="复制代码">📋 复制</button>`
  return (
    `<div class="md-code"${streaming ? ' data-streaming="1"' : ''}>` +
    `<div class="md-code-head"><span class="md-code-lang">${escapeHtml(label || 'text')}</span>` +
    `<span class="md-code-btns">${previewBtn}${copyBtn}</span></div>` +
    `<pre><code${hljsClass}>${bodyHtml}</code></pre>` +
    `</div>`
  )
}

// 自定义 fence：代码块加语言标签 + 复制按钮；html 代码块额外提供预览按钮；mermaid 特殊处理
md.renderer.rules.fence = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const lang = normalizeLang((token.info || '').trim().split(/\s+/)[0])
  const code = token.content
  // env.streaming：该片段尚未定稿（活动尾部的普通渲染）——
  // 不做语法高亮，避免每帧对同一段代码重复高亮
  const streaming = !!(env && env.streaming)

  // Mermaid：定稿后才渲染为图占位（由 renderMermaidBlocks 异步替换为 SVG）
  if (lang === 'mermaid') {
    if (props.done) {
      return `<div class="md-mermaid" data-src="${encodeURIComponent(code)}"><pre><code>${escapeHtml(code)}</code></pre></div>`
    }
    return codeBlockHtml('mermaid', escapeHtml(code), { streaming: true })
  }

  // 已定稿的分块：一次高亮到位（每个块只渲染一次，全生命周期 O(n) 总量）
  const body = streaming ? escapeHtml(code) : (highlightCode(code, lang) || escapeHtml(code))
  return codeBlockHtml(lang, body, {
    preview: lang === 'html',
    streaming,
    hljsClass: !streaming && lang ? ` class="hljs language-${escapeHtml(lang)}"` : '',
  })
}

// 表格包裹容器便于横向滚动
const defaultTableOpen = md.renderer.rules.table_open || ((tokens, idx, options, env, slf) => slf.renderToken(tokens, idx, options))
md.renderer.rules.table_open = (tokens, idx, options, env, slf) => '<div class="md-table-wrap">' + defaultTableOpen(tokens, idx, options, env, slf)
const defaultTableClose = md.renderer.rules.table_close || ((tokens, idx, options, env, slf) => slf.renderToken(tokens, idx, options))
md.renderer.rules.table_close = (tokens, idx, options, env, slf) => defaultTableClose(tokens, idx, options, env, slf) + '</div>'

// 外链新窗口打开
const defaultLinkOpen = md.renderer.rules.link_open || ((tokens, idx, options, env, slf) => slf.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, slf) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, slf)
}

let mermaidPromise = null
let mermaidSeq = 0
function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'strict',
        fontFamily: 'inherit',
      })
      return mermaid
    })
  }
  return mermaidPromise
}

async function renderMermaidBlocks() {
  const root = rootRef.value
  if (!root) return
  const blocks = root.querySelectorAll('.md-mermaid:not([data-rendered])')
  if (!blocks.length) return
  let mermaid
  try {
    mermaid = await getMermaid()
  } catch {
    return
  }
  for (const el of blocks) {
    el.setAttribute('data-rendered', '1')
    const src = decodeURIComponent(el.getAttribute('data-src') || '')
    try {
      const id = 'md-mermaid-' + ++mermaidSeq
      const { svg } = await mermaid.render(id, src)
      const box = document.createElement('div')
      box.className = 'md-mermaid-svg'
      box.innerHTML = svg
      el.replaceChildren(box)
    } catch (e) {
      el.classList.add('md-mermaid-error')
      const tip = document.createElement('div')
      tip.className = 'md-mermaid-error-tip'
      tip.textContent = '⚠️ Mermaid 图渲染失败：' + (e?.message || e)
      el.prepend(tip)
    }
  }
}

// ---------- 流式增量渲染引擎 ----------
// 设计见 plans/streaming-markdown-render-perf-plan.md：
//   1) 稳定前缀（.md-stable）只追加、永不重写 ⇒ 已定稿区域的滚动/选区/图片不受影响
//   2) 活动尾部（.md-live）只渲染"最后一个块"级别的小片段 ⇒ 单帧成本与消息总长解耦
//   3) 尾部是"未闭合代码块"时走 DOM 原地追加文本 ⇒ 连尾块自身的横向滚动位置也保留
//   4) 定稿（done）时整段一次性重渲 ⇒ 吸收分块带来的语义偏差，与"整段渲染"结果一致

const splitter = createStreamSplitter()

let renderedSrc = '' // 已渲染的完整源码：区分"追加"与"分叉/回退"（重试会清空 content）
let committed = 0 // 已提交进 .md-stable 的源码长度（分界点）
let liveMode = 'empty' // 尾部形态：empty | flow | fence
let fenceKey = '' // 未闭合代码块的头部（```lang）
let fenceBody = '' // 已写入 <code> 的正文，用于计算增量

let rafId = null
let pendingRender = false
let lastRenderTs = 0
let doneRendered = false

// 流式期间的最小渲染间隔（约 20fps）：文本追加在 15~20fps 下已足够顺滑，
// 能显著减少无效解析；定稿渲染不受此限制
const MIN_RENDER_INTERVAL = 50

// 每帧渲染一次 markdown，env 独立（不共享，避免跨片段残留状态）。
// 代价：跨块引用式链接 [x][1] 需等定稿整段重渲才能解析 —— 属可接受偏差
function mdRender(src, streaming) {
  return md.render(src, { streaming })
}

// 把新增的"块安全分界点之前"的内容渲染一次并追加进稳定容器
function appendStable(chunkSrc) {
  const el = stableRef.value
  if (!el || !chunkSrc) return
  let html
  try {
    html = mdRender(chunkSrc, false)
  } catch (e) {
    console.warn('[markdown] 分块渲染失败，退化为纯文本:', e)
    html = `<pre class="md-plain-fallback">${escapeHtml(chunkSrc)}</pre>`
  }
  el.insertAdjacentHTML('beforeend', html) // 只追加：既有 DOM 节点身份不变
}

function clearDom() {
  if (stableRef.value) stableRef.value.innerHTML = ''
  if (liveRef.value) liveRef.value.innerHTML = ''
  splitter.reset()
  committed = 0
  liveMode = 'empty'
  fenceKey = ''
  fenceBody = ''
}

/** 该行是否为与 marker 同符号、长度不短于 marker 的闭合围栏行 */
function isFenceClose(line, marker) {
  const t = line.trim()
  if (!t || t[0] !== marker[0] || t.length < marker.length) return false
  return t === marker[0].repeat(t.length)
}

/**
 * 判断一段源码是否"整体就是尚未闭合的围栏代码块"，是则返回可原地追加的头部与正文。
 * 已闭合（正文里已有闭合围栏）则返回 null，交给 markdown-it 正常渲染。
 */
function parseOpenFence(src) {
  const m = /^ {0,3}(`{3,}|~{3,})([^\n]*)/.exec(src)
  if (!m) return null
  const marker = m[2]
  const key = m[1] + marker + m[3]
  let bodyStart = m[0].length
  if (src[bodyStart] === '\r') bodyStart++
  if (src[bodyStart] === '\n') bodyStart++
  const body = src.slice(bodyStart)
  if (body.split('\n').some((line) => isFenceClose(line, marker))) return null
  const label = (m[3] || '').trim().split(/\s+/)[0].toLowerCase() || 'text'
  return { key, label, body }
}

function updateLiveFenceSkeleton(label) {
  const el = liveRef.value
  if (!el) return null
  el.innerHTML = codeBlockHtml(label, '', { streaming: true })
  return el.querySelector('pre code')
}

// 渲染活动尾部：优先走"未闭合代码块原地追加"，否则整块覆盖
function renderTail(tail) {
  const el = liveRef.value
  if (!el) return
  if (!tail) {
    if (liveMode !== 'empty') el.innerHTML = ''
    liveMode = 'empty'
    fenceKey = ''
    fenceBody = ''
    return
  }

  const open = parseOpenFence(tail)
  if (open) {
    let codeEl = null
    if (liveMode === 'fence' && fenceKey === open.key) {
      codeEl = el.querySelector('pre code')
    }
    if (!codeEl) {
      fenceBody = ''
      codeEl = updateLiveFenceSkeleton(open.label)
    }
    liveMode = 'fence'
    fenceKey = open.key
    if (codeEl) {
      if (open.body.startsWith(fenceBody)) {
        const delta = open.body.slice(fenceBody.length)
        if (delta) codeEl.appendChild(document.createTextNode(delta))
      } else {
        codeEl.textContent = open.body // 极少见：头部/正文被改写，整体回填
      }
      fenceBody = open.body
    }
    return
  }

  liveMode = 'flow'
  fenceKey = ''
  fenceBody = ''
  try {
    el.innerHTML = mdRender(tail, true) // streaming：未定稿片段不高亮、不画 Mermaid 图
  } catch (e) {
    console.warn('[markdown] 尾段渲染失败，退化为纯文本:', e)
    el.innerHTML = `<pre class="md-plain-fallback">${escapeHtml(tail)}</pre>`
  }
}

function doRender() {
  const stable = stableRef.value
  const live = liveRef.value
  if (!stable || !live) return
  const src = props.content || ''
  if (rootRef.value) rootRef.value.dataset.renderMode = props.done ? 'full' : 'incremental'

  // ---- 定稿：整段一次性渲染（与 Mermaid 的"完成后才画图"路径天然合并）----
  if (props.done) {
    if (doneRendered && src === renderedSrc) return
    try {
      stable.innerHTML = mdRender(src, false)
    } catch (e) {
      console.warn('[markdown] 整段渲染失败，退化为纯文本:', e)
      stable.innerHTML = `<pre class="md-plain-fallback">${escapeHtml(src)}</pre>`
    }
    live.innerHTML = ''
    splitter.reset()
    splitter.feed(src)
    committed = src.length
    liveMode = 'empty'
    fenceKey = ''
    fenceBody = ''
    renderedSrc = src
    doneRendered = true
    nextTick(renderMermaidBlocks)
    emit('rendered')
    return
  }
  doneRendered = false

  // 内容不是"在上次基础上追加"（重试清空、分段替换等）⇒ 整体重来，避免增量状态错位
  if (!src.startsWith(renderedSrc)) {
    clearDom()
    renderedSrc = ''
  }

  splitter.feed(src)
  const boundary = splitter.commitBoundary(src)
  if (boundary > committed) {
    appendStable(src.slice(committed, boundary))
    committed = boundary
    liveMode = 'flow'
    fenceKey = ''
    fenceBody = ''
  }
  renderTail(src.slice(committed))
  renderedSrc = src
  emit('rendered')
}

function safeRender() {
  try {
    doRender()
  } catch (e) {
    console.warn('[markdown] 渲染异常:', e)
  }
}

// 尾部异常长（如模型长时间不输出空行、整段是一个超长段落）时进一步降频，
// 避免退化成"每帧 O(尾长)"的高频重排
function currentInterval() {
  const tailLen = (props.content || '').length - committed
  return tailLen > 4000 ? 200 : MIN_RENDER_INTERVAL
}

function onFrame() {
  rafId = null
  if (!pendingRender) return
  if (!props.done && currentInterval() - (performance.now() - lastRenderTs) > 0) {
    rafId = requestAnimationFrame(onFrame) // 未到最小间隔：下一帧再看
    return
  }
  pendingRender = false
  lastRenderTs = performance.now()
  safeRender()
}

// rAF 节流 + 最小间隔：流式高频 delta 下合并渲染；
// 页面隐藏时只累积不渲染（数据在 store 侧持续累积，切回前台再补渲染，不会丢内容）
function scheduleRender() {
  pendingRender = true
  if (rafId !== null) return
  if (document.hidden) return
  rafId = requestAnimationFrame(onFrame)
}

function onVisibilityChange() {
  if (!document.hidden && pendingRender) scheduleRender()
}

watch(() => [props.content, props.done], scheduleRender, { flush: 'post' })
onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
  safeRender()
})
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  if (rafId !== null) cancelAnimationFrame(rafId)
  rafId = null
})

// ---------- HTML 代码块预览 ----------
// 优先方案（Electron 环境）：把代码块内容保存到 runtime/preview 目录下的 .html 文件，
// 由主进程在应用内独立 Electron 预览窗口打开 —— 脚本/样式/外部资源完整可运行。
// 回退方案（纯浏览器开发环境）：应用内 iframe 沙箱弹窗（sandbox="allow-scripts"，
// 不含 allow-same-origin，与宿主页面隔离，防 XSS）。
const previewVisible = ref(false)
const previewContent = ref('')
const previewPanelRef = ref(null)

async function openPreview(code) {
  const api = window.electronAPI
  if (api && typeof api.openHtmlPreview === 'function') {
    try {
      const res = await api.openHtmlPreview(code)
      if (res && res.success) return
      // 落盘/打开失败时回退到内置弹窗，保证功能可用
      console.warn('[md-preview] 外部预览失败，回退内置弹窗:', res && res.message)
    } catch (e) {
      console.warn('[md-preview] 外部预览异常，回退内置弹窗:', e)
    }
  }
  previewContent.value = code
  previewVisible.value = true
  nextTick(() => previewPanelRef.value?.focus())
}

function closePreview() {
  previewVisible.value = false
  previewContent.value = ''
}

// 预览/复制按钮（事件委托，v-html 内容无法直接绑定 Vue 事件）
async function onClick(e) {
  const pv = e.target.closest('.md-preview')
  if (pv) {
    const codeEl = pv.closest('.md-code')?.querySelector('pre code')
    if (codeEl) openPreview(codeEl.textContent || '')
    return
  }
  const btn = e.target.closest('.md-copy')
  if (!btn) return
  const codeEl = btn.closest('.md-code')?.querySelector('pre code')
  if (!codeEl) return
  const text = codeEl.innerText
  let ok = false
  try {
    await navigator.clipboard.writeText(text)
    ok = true
  } catch {
    // clipboard API 不可用时回退
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      ok = document.execCommand('copy')
      document.body.removeChild(ta)
    } catch { ok = false }
  }
  btn.classList.toggle('copied', ok)
  btn.classList.toggle('copy-fail', !ok)
  btn.textContent = ok ? '✓ 已复制' : '✗ 复制失败'
  setTimeout(() => {
    btn.classList.remove('copied', 'copy-fail')
    btn.textContent = '📋 复制'
  }, 1500)
}
</script>

<style>
/* 非 scoped：作用于 v-html 注入的内容 */
.markdown-body { white-space: normal; word-break: break-word; line-height: 1.7; font-size: 14px; }
.markdown-body > *:first-child { margin-top: 0; }
.markdown-body > *:last-child { margin-bottom: 0; }

/* 双容器增量渲染（.md-stable 只追加 / .md-live 覆盖尾部）：
   两个容器都是无 padding/border 的普通 div，子元素外边距会透过容器边界正常折叠，
   因此相邻块间距与"单容器整段渲染"一致；只有整篇的第一个/最后一个块需要单独归零 */
.markdown-body > .md-live:empty { display: none; }
.markdown-body > .md-stable > :first-child { margin-top: 0; }
.markdown-body > .md-live > :last-child { margin-bottom: 0; }
/* 定稿时（整篇都在 stable 内）末块不留外边距，与旧行为一致 */
.markdown-body.md-full > .md-stable > :last-child { margin-bottom: 0; }
/* 前缀为空时（流式最开始）live 即为文档起始，其首块不留上外边距 */
.markdown-body:has(> .md-stable:empty) > .md-live > :first-child { margin-top: 0; }
/* 渲染兜底：极端情况下退化为纯文本时的容器样式 */
.md-plain-fallback { margin: 0.5em 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; }
.markdown-body p { margin: 0.5em 0; }
.markdown-body h1, .markdown-body h2, .markdown-body h3,
.markdown-body h4, .markdown-body h5, .markdown-body h6 {
  margin: 1em 0 0.5em; line-height: 1.4; color: #f1f5f9; font-weight: 700;
}
.markdown-body h1 { font-size: 1.5em; border-bottom: 1px solid #334155; padding-bottom: 0.25em; }
.markdown-body h2 { font-size: 1.3em; border-bottom: 1px solid #334155; padding-bottom: 0.2em; }
.markdown-body h3 { font-size: 1.15em; }
.markdown-body h4, .markdown-body h5, .markdown-body h6 { font-size: 1.05em; }
.markdown-body ul, .markdown-body ol { margin: 0.5em 0; padding-left: 1.6em; }
.markdown-body li { margin: 0.2em 0; }
.markdown-body li > p { margin: 0.2em 0; }
.markdown-body blockquote {
  margin: 0.6em 0; padding: 0.4em 0.9em; border-left: 3px solid #6366f1;
  background: #0f172a99; color: #94a3b8; border-radius: 0 6px 6px 0;
}
.markdown-body blockquote p { margin: 0.2em 0; }
.markdown-body a { color: #818cf8; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body hr { border: none; border-top: 1px solid #334155; margin: 1em 0; }
.markdown-body strong { color: #f8fafc; }
.markdown-body img { max-width: 100%; border-radius: 8px; }
.markdown-body code:not(.hljs) {
  background: #33415580; border: 1px solid #334155; border-radius: 4px;
  padding: 0.1em 0.35em; font-size: 0.92em; color: #fbbf24;
  font-family: Consolas, 'Courier New', monospace;
}

/* 表格 */
.md-table-wrap { overflow-x: auto; margin: 0.6em 0; }
.markdown-body table { border-collapse: collapse; width: 100%; font-size: 0.95em; }
.markdown-body th, .markdown-body td { border: 1px solid #334155; padding: 6px 10px; text-align: left; }
.markdown-body th { background: #1e293b; color: #e2e8f0; font-weight: 600; }
.markdown-body tr:nth-child(even) td { background: #0f172a66; }

/* 代码块 */
.markdown-body .md-code {
  margin: 0.7em 0; background: #0b1120; border: 1px solid #334155;
  border-radius: 8px; overflow: hidden;
}
.markdown-body .md-code-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 10px; background: #1e293b; border-bottom: 1px solid #334155;
}
.markdown-body .md-code-lang { font-size: 12px; color: #64748b; text-transform: lowercase; }
.markdown-body .md-code-btns { display: flex; align-items: center; gap: 6px; }
.markdown-body .md-copy,
.markdown-body .md-preview {
  border: 1px solid #334155; background: transparent; color: #94a3b8;
  font-size: 12px; padding: 2px 10px; border-radius: 5px; cursor: pointer;
  opacity: 0; transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.markdown-body .md-code:hover .md-copy,
.markdown-body .md-code:hover .md-preview { opacity: 1; }
.markdown-body .md-copy:hover,
.markdown-body .md-preview:hover { background: #334155; color: #e2e8f0; }
.markdown-body .md-copy.copied { opacity: 1; color: #34d399; border-color: #065f46; }
.markdown-body .md-copy.copy-fail { opacity: 1; color: #f87171; border-color: #7f1d1d; }
.markdown-body .md-code pre {
  margin: 0; padding: 10px 12px; overflow-x: auto;
  background: transparent !important;
}
.markdown-body .md-code pre code {
  font-family: Consolas, 'Courier New', monospace; font-size: 13px;
  line-height: 1.55; background: transparent !important; padding: 0; white-space: pre;
}

/* Mermaid */
.markdown-body .md-mermaid {
  margin: 0.7em 0; padding: 10px; background: #0b1120; border: 1px solid #334155;
  border-radius: 8px; overflow-x: auto; text-align: center;
}
.markdown-body .md-mermaid pre { margin: 0; text-align: left; }
.markdown-body .md-mermaid-svg svg { max-width: 100%; height: auto; }
.markdown-body .md-mermaid-error-tip { color: #fbbf24; font-size: 12px; margin-bottom: 6px; text-align: left; }

/* KaTeX */
.markdown-body .katex { font-size: 1.06em; }
.markdown-body .katex-display { margin: 0.7em 0; overflow-x: auto; overflow-y: hidden; padding: 2px 0; }
.markdown-body .texmath { color: #e2e8f0; }

/* HTML 预览弹窗（Teleport 到 body，非 scoped） */
.md-preview-modal {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6); display: flex;
  align-items: center; justify-content: center; z-index: 1100;
}
.md-preview-panel {
  width: min(860px, 92vw); height: min(640px, 86vh);
  display: flex; flex-direction: column; background: #1e293b;
  border: 1px solid #334155; border-radius: 12px; overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5); outline: none;
}
.md-preview-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px; background: #172033; border-bottom: 1px solid #334155; flex-shrink: 0;
}
.md-preview-title { color: #e2e8f0; font-size: 13px; font-weight: 600; }
.md-preview-close {
  border: none; background: transparent; color: #94a3b8; cursor: pointer;
  font-size: 14px; padding: 4px 8px; border-radius: 6px;
}
.md-preview-close:hover { background: #334155; color: #e2e8f0; }
.md-preview-frame { flex: 1; width: 100%; border: none; background: #fff; }
</style>
