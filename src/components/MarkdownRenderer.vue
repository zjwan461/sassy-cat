<template>
  <div class="markdown-body" ref="rootRef" v-html="html" @click="onClick"></div>
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
import { ref, watch, nextTick, onMounted } from 'vue'
import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import hljs from 'highlight.js/lib/common'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/atom-one-dark.css'

const props = defineProps({
  // markdown 原文
  content: { type: String, default: '' },
  // 消息是否已完成（流式期间为 false：Mermaid 图延迟到完成后渲染）
  done: { type: Boolean, default: true },
})

const rootRef = ref(null)
const html = ref('')

function escapeHtml(s) {
  return s.replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>').replace(/"/g, '"')
}

const md = new MarkdownIt({
  html: false, // 禁止原始 HTML，防 XSS
  linkify: true,
  breaks: true, // 单个换行也换行，符合聊天习惯
  highlight(code, lang) {
    try {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value
      }
      return hljs.highlightAuto(code).value
    } catch {
      return escapeHtml(code)
    }
  },
})

md.use(texmath, {
  engine: katex,
  delimiters: ['dollars', 'brackets'], // $...$ / $$...$$ 与 \( \) / \[ \]
  katexOptions: { throwOnError: false, output: 'html' },
  classesForModern: false,
})

// 自定义 fence：代码块加语言标签 + 复制按钮；html 代码块额外提供预览按钮；mermaid 特殊处理
md.renderer.rules.fence = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const lang = (token.info || '').trim().split(/\s+/)[0].toLowerCase()
  const code = token.content
  // html/htm 代码块：右上角提供“预览”按钮，点击后在沙箱 iframe 中渲染
  const isHtmlBlock = lang === 'html' || lang === 'htm'
  const previewBtn = isHtmlBlock
    ? `<button class="md-preview" type="button" title="在弹窗中预览 HTML">🌐 预览</button>`
    : ''

  // Mermaid：完成后渲染为图占位（由 renderMermaid 异步替换为 SVG），流式期间按普通代码展示
  if (lang === 'mermaid') {
    if (props.done) {
      return `<div class="md-mermaid" data-src="${encodeURIComponent(code)}"><pre><code>${escapeHtml(code)}</code></pre></div>`
    }
    return `<div class="md-code" data-streaming="1"><div class="md-code-head"><span class="md-code-lang">mermaid</span></div><pre><code>${escapeHtml(code)}</code></pre></div>`
  }

  const highlighted = md.options.highlight
    ? md.options.highlight(code, lang)
    : escapeHtml(code)
  const body = highlighted || escapeHtml(code)
  return (
    `<div class="md-code">` +
    `<div class="md-code-head"><span class="md-code-lang">${escapeHtml(lang || 'text')}</span>` +
    `<span class="md-code-btns">${previewBtn}<button class="md-copy" type="button" title="复制代码">📋 复制</button></span></div>` +
    `<pre><code class="hljs${lang ? ' language-' + escapeHtml(lang) : ''}">${body}</code></pre>` +
    `</div>`
  )
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

// rAF 节流：流式高频 delta 下每帧最多重渲染一次
let rafId = null
let pending = false
function scheduleRender() {
  if (rafId !== null) {
    pending = true
    return
  }
  doRender()
}
function doRender() {
  rafId = null
  try {
    html.value = md.render(props.content || '')
  } catch {
    html.value = escapeHtml(props.content || '')
  }
  nextTick(() => {
    if (props.done) renderMermaidBlocks()
  })
  if (pending) {
    pending = false
    rafId = requestAnimationFrame(doRender)
  }
}

watch(() => [props.content, props.done], scheduleRender, { flush: 'post' })
onMounted(() => {
  html.value = md.render(props.content || '')
  nextTick(renderMermaidBlocks)
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
